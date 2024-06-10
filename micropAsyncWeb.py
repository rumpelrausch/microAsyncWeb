import uasyncio as asyncio
import uerrno
import json
import re


def dirname(string):
    return "/".join(string.split("/")[:-1])


class HttpError(Exception):
    pass


class Request:
    url = ""
    path = ""
    method = ""
    version = ""
    headers = {}
    route = ""
    params = None
    read = None
    write = None
    close = None

    def __init__(self):
        self.headers = {}
        self.route = ""
        self.params = []

    async def setup(self, reader, writer):
        self.read = reader.read
        self.write = writer.awrite
        self.close = writer.aclose

        items = await reader.readline()
        items = items.decode("ascii").split()
        if len(items) != 3:
            return

        self.method, self.url, self.version = items
        self.path = self.url.replace("?", "#").split("#")[0]

    def getFilename(self):
        return self.path.split("/")[-1]

    def getFileExtension(self, filename=""):
        if filename == "":
            filename = self.getFilename()
        return filename.split(".")[-1]


class Response:
    fileTypes = {
        "txt": {"binary": False, "blockSize": 64, "mimeType": "text/plain"},
        "htm": {"binary": False, "blockSize": 64, "mimeType": "text/html"},
        "html": {"binary": False, "blockSize": 64, "mimeType": "text/html"},
        "css": {"binary": False, "blockSize": 64, "mimeType": "text/css"},
        "js": {"binary": False, "blockSize": 64, "mimeType": "text/javascript"},
        "json": {"binary": False, "blockSize": 64, "mimeType": "application/json"},
        "ico": {
            "binary": True,
            "blockSize": 1024,
            "mimeType": "image/vnd.microsoft.icon",
        },
        "jpg": {"binary": True, "blockSize": 1024, "mimeType": "image/jpeg"},
        "png": {"binary": True, "blockSize": 1024, "mimeType": "image/png"},
        "gif": {"binary": True, "blockSize": 1024, "mimeType": "image/gif"},
        "webp": {"binary": True, "blockSize": 1024, "mimeType": "image/webp"},
        "ttf": {"binary": True, "blockSize": 1024, "mimeType": "font/ttf"},
        "otf": {"binary": True, "blockSize": 1024, "mimeType": "font/otf"},
        "woff": {"binary": True, "blockSize": 1024, "mimeType": "font/woff"},
        "woff2": {"binary": True, "blockSize": 1024, "mimeType": "font/woff2"},
    }

    @staticmethod
    async def start(request, statusCode, statusText):
        await request.write("HTTP/1.1 %s %s\r\n" % (statusCode, statusText))

    @staticmethod
    async def startBody(request):
        await request.write("\r\n")

    @staticmethod
    async def sendJson(request, dict):
        await Response.start(request, 200, "OK")
        await request.write("Content-type: application/json;charset=utf-8\r\n")
        await Response.startBody(request)
        await request.write("{0}".format(json.dumps(dict)))

    @staticmethod
    async def sendFile(request, filename):
        args = {
            "blockSize": 64,
            "binary": False,
            "mimeType": "application/octet-stream",
        }
        try:
            extension = request.getFileExtension(filename)
            if extension in Response.fileTypes:
                args = args | Response.fileTypes[extension]
            with open(filename, "rb" if args["binary"] else "r") as fileHandle:
                await Response.start(request, 200, "OK")
                await request.write("Content-type: %s\r\n" % (args["mimeType"]))
                await Response.startBody(request)
                while True:
                    data = fileHandle.read(args["blockSize"])
                    if not data:
                        break
                    await request.write(data)
        except OSError as e:
            if e.args[0] != uerrno.ENOENT:
                raise
            raise HttpError(request, 404, "File Not Found")

    @staticmethod
    async def write(request, data):
        await request.write(data.encode("utf-8") if type(data) == str else data)

    @staticmethod
    async def error(request, code, reason):
        await request.write("HTTP/1.1 %s %s\r\n\r\n" % (code, reason))
        await request.write("<h1>%s</h1>" % (reason))


class MicropAsyncWeb:

    requestHeadersToKeep = ("Authorization", "Content-Length", "Content-Type")
    headers = {}

    def __init__(self, port=80, address="0.0.0.0", webroot=".", indexFile="index.html"):
        self.port = port
        self.address = address
        self.webroot = webroot
        self.indexFile = indexFile
        self.routes = [
            ["/", self.fileRouteHandler, "GET"],
            ["/*", self.fileRouteHandler, "GET"],
        ]

    def appendRoutes(self, routes):
        for route in routes:
            if len(route) < 3:
                route.append("GET")
            self.routes.append(route[:3])

    def sortRoutes(self):
        def routeSorter(routeConfig):
            return len(routeConfig[0].replace("*", "/").split("/"))

        self.routes = sorted(self.routes, key=routeSorter, reverse=False)

    def compileRegexRoutes(self):
        for routeConfig in self.routes:
            route = routeConfig[0]
            if "*" in route:
                routeConfig.append(re.compile("^" + route.replace("*", "([^/]+)") + "$"))

    async def fileRouteHandler(self, request):
        filename = request.getFilename()
        if filename == "":
            filename = self.indexFile
        await Response.sendFile(request, "%s/%s" % (self.webroot, filename))

    def route(self, route, methods="GET"):
        def decorator(func):
            self.routes.append([route, func, methods])
            return func

        return decorator

    async def generateOutput(self, request, handler):
        """Generate output from handler

        `handler` can be :
         * string, considered as a path to a file
         * callable, the output of which is sent to the client
        """
        while handler:
            if isinstance(handler, str):
                await Response.sendFile(request, handler)
                break

            handler = await handler(request)

    async def handle(self, reader, writer):
        request = Request()
        await request.setup(reader, writer)

        try:
            try:
                if request.version not in ("HTTP/1.0", "HTTP/1.1"):
                    raise HttpError(request, 505, "Version Not Supported")

                while True:
                    items = await reader.readline()
                    items = items.decode("ascii").split(":", 1)

                    if len(items) == 2:
                        header, value = items
                        value = value.strip()

                        if header in self.requestHeadersToKeep:
                            request.headers[header] = value
                    elif len(items) == 1:
                        break

                found = False
                for routeConfig in self.routes:
                    route = routeConfig[0]
                    handler = routeConfig[1]
                    # print("trying {0}".format(routeConfig))

                    if len(routeConfig) > 2:
                        if request.method not in routeConfig[2].split(","):
                            continue

                    if request.path == route:
                        # print("1 route={0}".format(route))
                        found = True
                        await self.generateOutput(request, handler)
                        break

                    if len(routeConfig) > 3:
                        # has regex
                        match = routeConfig[3].match(request.path)
                        if match:
                            try:
                                for group in range(1, route.count("*") + 1):
                                    request.params.append(match.group(group))
                                request.route = route
                                found = True
                                await self.generateOutput(request, handler)
                                break
                            except:
                                request.params = []

                if not found:
                    raise HttpError(request, 404, "File Not Found")
            except HttpError as e:
                request, code, message = e.args
                await Response.error(request, code, message)
        except OSError as e:
            # Skip ECONNRESET error (client abort request)
            if e.args[0] != uerrno.ECONNRESET:
                raise
        finally:
            await writer.aclose()

    async def runAsync(self):
        self.compileRegexRoutes()
        self.sortRoutes()
        return await asyncio.start_server(self.handle, self.address, self.port)
