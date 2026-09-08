# File Browser FTPS access

![File Browser FTPS access](webui/thumbnail.webp)

Explicit FTPS with certificate-verified TLS on control and data connections.

## Compatibility

**Requires Agent Zero v2.12 or later.**

## Install and configure

Install this repository through Agent Zero's Plugin Hub Git URL installer. Enable the plugin globally, then open its settings and choose **Open connection settings**, or use **Files → Settings → Add connection** and select this transport.

Enter server, port (21), absolute folder, registered username and password. The server must support explicit TLS, private data channels, passive transfers and MLSD. An optional trusted CA file is an absolute path inside the Agent Zero instance. Plain FTP, anonymous accounts and implicit port-990 FTPS are not supported.

Dependencies: Python standard library (ftplib and ssl); no package installation needed. This plugin needs no install hook because it uses only the Python standard library.

## Use and permissions

Save a named connection, test it, then use the folder icon in the connection list. Each connection has independent Browse, Download, Upload/create, Edit, Rename/move and Delete controls; unsupported actions are disabled. Browse and Download default on; mutations default off. Text and code files open in the shared Editor. Files supports list/icon views and the optional file tree for remote connections.

Permissions constrain File Browser operations, not arbitrary agent shell tools or server accounts. Editing necessarily reveals file content. Credentials are stored privately (0600) under this plugin's `data/connections.json` and are omitted from browser responses. An unchanged secret retains its saved value; replacing it updates it. Protect the instance and its backups.

## Limits

FTPS has no standard conditional rename. New writes and moves check for existing destinations, but another client can race those checks. Edits use a temporary upload and content-hash check before RNTO. Servers unable to replace via RNTO fail without deleting the original. Use a server-side jailed account; only ordinary MLSD files/directories are listed. No symlink traversal is intended, but server-side path confinement is authoritative.

Shared Files limits: 100 MiB uploads/download archives, 1000 archive entries, nesting depth 64; Editor supports UTF-8 nonbinary files up to 1 MiB. Cross-connection moves and remote-to-local Save As are not supported. Use download/upload to transfer between connection types. Internet access to the configured server is required; storage/network charges remain your provider's responsibility.

## Verification

Actual isolated FTP server verifies TLS on control and data channels, read/create/save/rename/delete, stale-save and duplicate-create rejection, and untrusted certificate rejection. Run `python -m unittest -v test_transport` from the repository with the framework interpreter; OpenSSL creates a disposable test certificate.

Before production use, test a disposable folder on your actual server: listing, new upload, Editor save, duplicate destination rejection, stale-save rejection, download, rename where supported, and deletion. Confirm denied actions remain denied and disable the plugin to confirm connections become unavailable. Protocol differences and server permissions matter.

## Disable and remove

Disabling hides this provider and rejects further connection operations. Removing a connection deletes its saved credentials. Uninstalling deletes the plugin directory, including saved connections and any plugin-owned key; back up what you need first. Shared Python dependencies are not uninstalled because other plugins may use them. No service, mount or system symlink is created. Legacy SSH data is preserved during migration and is not removed by uninstall.

## License

MIT. See [LICENSE](LICENSE). Agent Zero-derived integration retains its upstream license notice.
