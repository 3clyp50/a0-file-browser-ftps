"""Explicit FTPS with verified TLS on control and data channels."""
import datetime
import ftplib
import hashlib
import posixpath
import ssl
import uuid
from contextlib import contextmanager

from helpers.file_transfers import TransferWriter


class Provider:
    id = "ftps"
    plugin_name = "file_browser_ftps"
    title = "FTPS (explicit TLS)"
    fields = [
        {"name": "host", "label": "Server name", "default": ""},
        {"name": "port", "label": "Port", "type": "number", "default": 21},
        {"name": "root", "label": "Remote folder", "default": "/"},
        {"name": "username", "label": "Username", "default": ""},
        {"name": "password", "label": "Password", "secret": True},
        {"name": "ca_file", "label": "Trusted CA file (optional)", "default": "", "advanced": True},
    ]

    def validate(self, config):
        result = {field["name"]: str(config.get(field["name"], field.get("default", ""))) for field in self.fields}
        if not all(result[key].strip() for key in ("host", "username", "password")):
            raise ValueError("Server, username and password are required.")
        if result["username"].lower() in ("anonymous", "ftp", "guest"):
            raise ValueError("Use a registered FTPS account.")
        if any(char in result["host"] for char in '/\\\x00\r\n'):
            raise ValueError("Enter a server name, not a URL.")
        result["port"] = int(result["port"])
        if not 1 <= result["port"] <= 65535:
            raise ValueError("Invalid port.")
        root = result["root"]
        if not root.startswith("/") or any(part in (".", "..") for part in root.split("/")) or any(c in root for c in '\\\0\r\n'):
            raise ValueError("Use an absolute remote folder without parent traversal.")
        result["root"] = root.rstrip("/") or "/"
        return result

    @contextmanager
    def open(self, config, directory):
        client = ftplib.FTP_TLS(context=ssl.create_default_context(cafile=config.get("ca_file") or None), timeout=30)
        try:
            client.connect(config["host"], config["port"])
            client.login(config["username"], config["password"])
            client.prot_p()
            client.set_pasv(True)
            client.cwd(config["root"])
            yield FTPS(client, client.pwd())
        finally:
            client.close()


class FTPS:
    def __init__(self, client, root):
        self.client, self.root = client, root.rstrip("/") or "/"

    def path(self, relative):
        if any(c in relative for c in '\\\0\r\n') or any(p in (".", "..") for p in relative.split("/")):
            raise ValueError("Invalid FTPS path.")
        return posixpath.join(self.root, relative)

    def list(self, relative):
        # Check each directory component against MLSD; links are never traversed.
        if relative:
            self.stat(relative)
        result = []
        for name, facts in self.client.mlsd(self.path(relative), facts=["type", "size", "modify"]):
            kind = facts.get("type")
            if kind not in ("file", "dir"):
                continue
            try:
                modified = datetime.datetime.strptime(facts.get("modify", "").split(".")[0], "%Y%m%d%H%M%S").replace(tzinfo=datetime.timezone.utc).timestamp() * 1000
            except ValueError:
                modified = 0
            result.append(dict(name=name, is_dir=kind == "dir", size=int(facts.get("size", 0)), modified=modified))
        return result

    def stat(self, relative):
        if not relative:
            return dict(is_dir=True, size=0, modified=0)
        for item in self.list(posixpath.dirname(relative)):
            if item["name"] == posixpath.basename(relative):
                return item
        raise FileNotFoundError(relative)

    def read(self, relative, destination, limit):
        info = self.stat(relative)
        if info["is_dir"] or (limit is not None and info["size"] > limit):
            raise ValueError("Not a file, or file exceeds the size limit.")
        output = TransferWriter(destination, limit)
        self.client.retrbinary("RETR " + self.path(relative), output.write)
        return output.receipt()["sha256"]

    def absent(self, relative):
        try:
            self.stat(relative)
        except FileNotFoundError:
            return
        raise FileExistsError("The destination already exists.")

    def write(self, relative, source, expected=None):
        self.stat(posixpath.dirname(relative))
        if expected is None:
            self.absent(relative)
        temporary = relative + ".a0-" + uuid.uuid4().hex
        try:
            digest = hashlib.sha256()
            self.client.storbinary("STOR " + self.path(temporary), source, callback=digest.update)
            if expected is not None:
                if self.read(relative, None, None) != expected:
                    raise ValueError("Remote file changed. Reopen it before saving.")
            else:
                self.absent(relative)
            # Servers unable to replace through RNTO fail without deleting the original.
            self.client.rename(self.path(temporary), self.path(relative))
        finally:
            try:
                self.client.delete(self.path(temporary))
            except ftplib.error_perm:
                pass
        return digest.hexdigest()

    def mkdir(self, relative):
        self.stat(posixpath.dirname(relative))
        self.absent(relative)
        self.client.mkd(self.path(relative))

    def rename(self, source, destination):
        self.stat(source)
        self.stat(posixpath.dirname(destination))
        self.absent(destination)
        self.client.rename(self.path(source), self.path(destination))

    def remove(self, relative, directory=False):
        self.stat(relative)
        operation = self.client.rmd if directory else self.client.delete
        operation(self.path(relative))
