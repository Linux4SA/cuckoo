import os
import sys
import socket
import platform
import xmlrpclib
import subprocess
import ConfigParser
from StringIO import StringIO
from zipfile import ZipFile, BadZipfile, ZIP_DEFLATED
from SimpleXMLRPCServer import SimpleXMLRPCServer

BIND_IP = "0.0.0.0"
BIND_PORT = 8000

STATUS_INIT = 0x0001
STATUS_RUNNING = 0x0002
STATUS_COMPLETED = 0x0003

CURRENT_STATUS = STATUS_INIT

class Agent:
    def __init__(self):
        self.error = ""
        self.system = platform.system().lower()
        self.analyzer_path = ""
        self.analyzer_pid = 0

    def _get_root(self, root="", container="cuckoo", create=True):
        if not root:
            if self.system == "windows":
                root = os.path.join(os.environ["SYSTEMDRIVE"] + os.sep, container)
            elif self.system == "linux" or self.system == "darwin":
                root = os.path.join(os.environ["HOME"], container)

        if create and not os.path.exists(root):
            try:
                os.makedirs(root)
            except OSError as e:
                self.error = e
                return False

        return root

    def get_status(self):
        return CURRENT_STATUS
   
    def get_error(self):
        # TODO need to fix this, sometimes string sometimes list/dict
        return "%s" % self.error

    def add_malware(self, data, name, iszip=False):
        data = data.data
        root = self._get_root(container="")

        if not root:
            return False

        if iszip:
            try:
                zip_data = StringIO()
                zip_data.write(data)
            
                with ZipFile(zip_data, "r") as archive:
                    try:
                        archive.extractall(root)
                    except BadZipfile as e:
                        self.error = e
                        return False
                    except RuntimeError:
                        try:
                            archive.extractall(path=root, pwd="infected")
                        except RuntimeError as e:
                            self.error = e
                            return False
            finally:
                zip_data.close()
        else:
            file_path = os.path.join(root, name)

            with open(file_path, "wb") as malware:
                malware.write(data)

        return True

    def add_config(self, options):
        root = self._get_root(container="analyzer")
        
        if not root:
            return False

        if type(options) != dict:
            return False

        config = ConfigParser.RawConfigParser()
        config.add_section("analysis")
        
        for key, value in options.items():
            config.set("analysis", key, value)
        
        config_path = os.path.join(root, "analysis.conf")
        with open(config_path, "wb") as config_file:
            config.write(config_file)
        
        return True

    def add_analyzer(self, data):
        data = data.data
        root = self._get_root(container="analyzer")

        if not root:
            return False

        try:
            zip_data = StringIO()
            zip_data.write(data)

            with ZipFile(zip_data, "r") as archive:
                archive.extractall(root)
        finally:
            zip_data.close()

        self.analyzer_path = os.path.join(root, "analyzer.py")

        return True

    def execute(self):
        global CURRENT_STATUS

        if not self.analyzer_path or not os.path.exists(self.analyzer_path):
            return False

        try:
            proc = subprocess.Popen([sys.executable, self.analyzer_path], cwd=os.path.dirname(self.analyzer_path))
            self.analyzer_pid = proc.pid
        except OSError as e:
            self.error = e
            return False

        CURRENT_STATUS = STATUS_RUNNING

        return self.analyzer_pid

    def complete(self):
        global CURRENT_STATUS
        CURRENT_STATUS = STATUS_COMPLETED
        return True

    def get_results(self):
        root = self._get_root(container="cuckoo", create=False)

        if not os.path.exists(root):
            return False

        zip_data = StringIO()
        zip_file = ZipFile(zip_data, "w", ZIP_DEFLATED)

        root_len = len(os.path.abspath(root))
        
        for root, dirs, files in os.walk(root):
            archive_root = os.path.abspath(root)[root_len:]
            for name in files:
                path = os.path.join(root, name)
                archive_name = os.path.join(archive_root, name)
                zip_file.write(path, archive_name, ZIP_DEFLATED)
        
        zip_file.close()
        data = xmlrpclib.Binary(zip_data.getvalue())
        zip_data.close()

        return data

if __name__ == "__main__":
    try:
        if not BIND_IP:
            BIND_IP = socket.gethostbyname(socket.gethostname())

        print("[+] Starting agent on %s:%s ..." % (BIND_IP, BIND_PORT))

        server = SimpleXMLRPCServer((BIND_IP, BIND_PORT))
        server.register_instance(Agent())
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
