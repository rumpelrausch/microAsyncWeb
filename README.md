# microAsyncWeb

A MicroPython web server using async.<br>
Does not block REPL/WebREPL.<br>
Code size is less than 9KB.

Based upon https://github.com/hugokernel/micropython-nanoweb.

## Features

- Runs fully async via MicroPython `uasyncio`.
- Also works as Thread, e.g. on second ESP32 core.
- Does not block REPL/WebREPL when started as thread.<br>
    Can be run together with other REPL tools like Thonny.
- Runs in parallel with pure async ftp servers (as long as RAM lasts).
- Automatically handles basic mime types.
- Automatically handles file delivery from a definable web root directory.
- Routes are configurable as lists or decorated functions.
- Extracts route parameters.

## Async invocation
```python
import asyncio
from micropAsyncWeb import MicropAsyncWeb, Response

webserver = MicropAsyncWeb()

# ...define your routes...

loop = asyncio.get_event_loop()
loop.create_task(webserver.runAsync())
# add any other async tasks
loop.run_forever()
```

## Threaded async invocation
```python
import asyncio
from micropAsyncWeb import MicropAsyncWeb, Response
from _thread import start_new_thread

webserver = MicropAsyncWeb()

# ...define your routes...

def runThread():
    loop = asyncio.get_event_loop()
    loop.create_task(webserver.runAsync())
    # add any other _thread compatible async tasks
    loop.run_forever()

start_new_thread(runThread, ())
```

## Examples

### Basic setup

```python
from micropAsyncWeb import MicropAsyncWeb, Response

# Automatically handles "/" and "/*" routes (deliver files from webroot).
webserver = MicropAsyncWeb(webroot="./webroot", indexFile="index.htm")

@webserver.route("/ping")
async def _route_ping(request):
    await Response.start(request, 200, "OK")
    await Response.startBody(request)
    await request.write("pong")
```

### Routes as list
```python
@webserver.route("/ping")
async def _route_ping(request):
    await Response.start(request, 200, "OK")
    await Response.startBody(request)
    await request.write("pong")

async def _route_info(request):
    await Response.sendJson(request, {"version": "0.0.1"})

# appendRoutes and decorators can be mixed
webserver.appendRoutes(
    [
        ["/api/v1/info", _route_info]
    ]
)
```

### Request methods and parameters
Decorated:
```python
@webserver.route("/api/v1/led/*/*", "POST")
async def _route_set_led(request):
    ledNum = int(request.params[0])
    ledState = int(request.params[0])
    result = myLedClass.setLed(ledNum, ledState)
    await Response.sendJson(request, result)
```

Using `appendRoutes`:
```python
async def _route_set_led(request):
    ledNum = int(request.params[0])
    ledState = int(request.params[0])
    result = myLedClass.setLed(ledNum, ledState)
    await Response.sendJson(request, result)

webserver.appendRoutes(
    [
        ["/api/v1/led/*/*", _route_set_led, "POST"]
    ]
)
```

## Reference

### Route definitions

Routes used in `.appendRoutes` are defined as _lists_ with two or three
entries:

0. `<str>` Route string
1. `<callable>` Route handler
2. `<str>` _optional_ Allowed http methods (comma separated list)

Routes used in decorators are defined by one or two positional
parameters:

0. `<str>` Route string
1. `<str>` _optional_ Allowed http methods (comma separated list)

If the http methods aren't defined "GET" will be assumed.

### Route syntax

- A route must begin with slash "/".
- A route may contain positional parameter placeholders as as single
  asterisk ("*").
- An asterisk placeholder must stand alone; `/some/route/px*` or
  `/route/**/a` are not allowed.
- Placeholders may be succeeded by additional paths, e.g.
  `/some/feature/*/detail/*`

### Route hierarchy

Routes are sorted automatically by their complexity.
If you need to define a specific route order you'll have to remove
the call to `self.sortRoutes()` at the end of the file.

### Class MicropAsyncWeb

#### Constructor
`(self, port=80, address="0.0.0.0", webroot=".", indexFile="index.html")`

There is no list of index files; You need to explicitely specify it.

#### appendRoutes
`.appendRoutes(<list>)`

See examples.

### Class Request

MicropAsyncWeb passes an instance of `Request` to the route handler.
It is set up with these members:

- `<str>` **`url`**<br>
    The full requested URL.
- `<str>` **`path`**<br>
    The path part without query parameters and hashes.
- `<str>` **`method`**<br>
    The requested http method.
- `<dict>` **`header`**<br>
    Incoming request headers. The allowed header list is filtered, see
    source code.
- `<list>` **`params`**<br>
    Each "*" in a given route is parsed as positional parameter and
    added to `.params`. See examples.
- `<callable>` **`write`**<br>
    Write directly to response stream.

### Class Response

This class is never instantiated; It's methods are static.

`start(request, statusCode, statusText)`<br>
Starts a response; The header section remains open.

`startBody(request)`<br>
Ends the header section.

`sendJson(request, dict)`<br>
Sends a full JSON response form a given dictionary, including response
start, header and body sections.

`sendFile(request, filename)`<br>
Sends a file. Uses the file name extension as hint for content-type
mime mapping.

`write(request, data)`<br>
Writes out an UTF-8 encoded string. Does not invoke `start()` or
`startBody()`.

`error(request, code, reason)`<br>
Sends a full error response, including response start, header and body
sections.
