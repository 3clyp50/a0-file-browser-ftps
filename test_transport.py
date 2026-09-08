"""Verified TLS control/data channels against a disposable FTP server."""
import hashlib
import socket
import socketserver
import ssl
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from backend import Provider


class TransportTest(unittest.TestCase):
    def test_encrypted_round_trip_and_conflict(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); cert=root/"cert.pem"; key=root/"key.pem"
            subprocess.run(["openssl","req","-x509","-newkey","rsa:2048","-nodes","-keyout",str(key),"-out",str(cert),"-days","1","-subj","/CN=localhost","-addext","subjectAltName=DNS:localhost"],check=True,capture_output=True)
            context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(cert,key)
            content={}; protected=[]
            class Handler(socketserver.BaseRequestHandler):
                def handle(self):
                    control=self.request; reader=control.makefile("rb"); data_listener=None; source=""; tls=False; private=False
                    def reply(message): control.sendall((message+"\r\n").encode())
                    reply("220 Test FTP")
                    try:
                        while True:
                            raw=reader.readline()
                            if not raw: break
                            command,_,arg=raw.decode().rstrip("\r\n").partition(" ")
                            if command=="AUTH":
                                reply("234 TLS"); reader.close(); control=context.wrap_socket(control,server_side=True);reader=control.makefile("rb");tls=True
                            elif command=="USER": reply("331 Password")
                            elif command=="PASS": reply("230 Logged in" if tls and arg=="test" else "530 Denied")
                            elif command in ("PBSZ","TYPE","OPTS"): reply("200 OK")
                            elif command=="PROT": private=arg=="P";reply("200 OK")
                            elif command=="CWD": reply("250 OK")
                            elif command=="PWD": reply('257 "/"')
                            elif command=="PASV":
                                data_listener=socket.socket();data_listener.bind(("127.0.0.1",0));data_listener.listen(1)
                                port=data_listener.getsockname()[1];reply(f"227 Entering Passive Mode (127,0,0,1,{port//256},{port%256})")
                            elif command in ("MLSD","RETR","STOR"):
                                reply("150 Data")
                                conn,_=data_listener.accept();data_listener.close();data_listener=None
                                if private: conn=context.wrap_socket(conn,server_side=True)
                                protected.append(tls and private)
                                if command=="MLSD":
                                    conn.sendall(''.join(f"type=file;size={len(value)};modify=20260908000000; {name.lstrip('/')}\r\n" for name,value in content.items()).encode())
                                elif command=="RETR": conn.sendall(content[arg])
                                else:
                                    value=bytearray()
                                    while chunk:=conn.recv(8192): value.extend(chunk)
                                    content[arg]=bytes(value)
                                if private: conn=conn.unwrap()
                                conn.close();reply("226 Complete")
                            elif command=="RNFR": source=arg;reply("350 Rename")
                            elif command=="RNTO": content[arg]=content.pop(source);reply("250 Renamed")
                            elif command=="DELE":
                                if arg in content: del content[arg];reply("250 Deleted")
                                else: reply("550 Missing")
                            else: reply("502 Unsupported")
                    except ssl.SSLError:
                        pass
                    finally:
                        reader.close();control.close()
                        if data_listener: data_listener.close()
            server=socketserver.ThreadingTCPServer(("127.0.0.1",0),Handler)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                config=Provider().validate(dict(host="localhost",port=server.server_address[1],root="/",username="test",password="test",ca_file=str(cert)))
                with Provider().open(config,root) as fs:
                    fs.write("code.py",b"print(1)")
                    data,revision=fs.read("code.py",1024)
                    self.assertEqual(data,b"print(1)")
                    fs.write("code.py",b"print(2)",expected=revision)
                    with self.assertRaises(ValueError): fs.write("code.py",b"stale",expected=revision)
                    self.assertEqual(content["/code.py"],b"print(2)")
                    with self.assertRaises(FileExistsError): fs.write("code.py",b"overwrite")
                    fs.rename("code.py","renamed.py");fs.remove("renamed.py")
                self.assertFalse(content)
                self.assertTrue(protected and all(protected))
                config["ca_file"]=""
                with self.assertRaises(ssl.SSLCertVerificationError):
                    with Provider().open(config,root): pass
            finally:
                server.shutdown();server.server_close();thread.join()


if __name__ == "__main__": unittest.main()
