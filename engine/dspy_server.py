"""
Example of a simple TCP server that is written in (mostly) coroutine
style and uses asyncio.streams.start_server() and
asyncio.streams.open_connection().

Note that running this example starts both the TCP server and client
in the same process.  It listens on port 12345 on 127.0.0.1, so it will
fail if this port is currently in use.
"""

import sys
import asyncio
import asyncio.streams
import struct
import concurrent.futures
import time
import numpy as np

IMAGE_DATA = 104
IMAGE_END = 105

def reverse_rows(width, height):
    for y in range(height):
        for x in range(width):
            yield ((height - y - 1) * width + x)*4
    #return [((height - y - 1) * width + x)*4 for y in range(height) for x in range(width)]

def get_pixel_data(pixel_data, width, height):
    return [(pixel_data[i+1], 
                pixel_data[i+2], 
                pixel_data[i+3], 
                pixel_data[i]) for i in reverse_rows(width,height)]

def reversed(buffer, width, height):
    return np.flipud(buffer).reshape((width+1)*(height+1), 4)

class DisplayServer:
    """
    This is just an example of how a TCP server might be potentially
    structured.  This class has basically 3 methods: start the server,
    handle a client, and stop the server.

    Note that you don't have to follow this structure, it is really
    just an example or possible starting point.
    """

    def __init__(self, engine, port, prman):
        self.server = None # encapsulates the server sockets
        self.engine = engine
        self.port = port
        # this keeps track of all the clients that connected to our
        # server.  It can be useful in some cases, for instance to
        # kill client connections or to broadcast some data to all
        # clients...
        self.clients = {} # task -> (reader, writer)
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.reading = False
        self.process_status = None
        self.process_time = 0
        self.prman = prman
        self.buffer = []
        self.fast_mode = True

    def _accept_client(self, client_reader, client_writer):
        """
        This method accepts a new client connection and creates a Task
        to handle this client.  self.clients is updated to keep track
        of the new client.
        """

        # start a new Task to handle this specific client connection
        print('accepting client')

        task = asyncio.Task(self._handle_client(client_reader, client_writer))
        self.clients[task] = (client_reader, client_writer)

        def client_done(task):
            print("client task done:", task, file=sys.stderr)
            if len(self.clients) == 1:
                loop = asyncio.get_event_loop()
                loop.stop()
            del self.clients[task]

        task.add_done_callback(client_done)

    def process_bucket(self, w_xmin, w_xmax, w_ymin, w_ymax, pixels):
        t = time.time()
        width = w_xmax - w_xmin + 1
        height = w_ymax - w_ymin + 1

        pixels = np.array(struct.unpack("f" * self.num_channels * width * height, pixels)).reshape((height, width, 4))
        tmp = np.copy(pixels[:,:, 0])
        pixels[:,:, 0] = pixels[:,:, 3]
        pixels[:,:, 3] = tmp
        if self.fast_mode:
            self.buffer[w_ymin: w_ymax + 1, w_xmin: w_xmax+1] = pixels
        else:
            result = self.engine.begin_result(w_xmin, self.ymax - w_ymax, width, height)
            result.layers[0].passes[0].rect = [(pix[1], pix[2], pix[3], pix[0]) for pix in [struct.unpack("f"* self.num_channels, pixels[4*i:4*i+16]) for i in reverse_rows(width, height)]]#copy_buffer(pixel_data))
            self.engine.end_result(result)
        self.process_time += time.time() - t
        self.prman.RicProcessCallbacks()

    async def _handle_client(self, client_reader, client_writer):
        """
        This method actually does the work to handle the requests for
        a specific client.  The protocol is line oriented, so there is
        a main loop that reads a line with a request and then sends
        out one or more lines back to the client with the result.
        """
        print('starting client')
        sep = b';'
        is_ready = False
        loop = asyncio.get_event_loop()
        display_done = False

        last_update = time.time()
        while not display_done:
            if not is_ready:
                data = (await client_reader.read(1024)).split(sep)

                image_name = data[0].decode()[1:]
                #image_name = (yield from client_reader.readuntil(sep)).decode("utf-8")
                #print("Image name", image_name)
                #dspy_params = (yield from client_reader.readuntil(sep)).decode("utf-8")
                dspy_params = data[2]
                #print("dspy params", dspy_params)
                
                xmin, xmax, ymin, ymax, a_len, z_len, channel_len, num_channels, merge = struct.unpack("!IIIIIIIIb", data[2][1:])
                pixel_size = int(a_len/8) + int(z_len/8) + int(channel_len/8 * num_channels) #bits ->bytes
                num_channels = num_channels + 1 if a_len > 0 else num_channels
                num_channels = num_channels + 1 if z_len > 0 else num_channels
                pixel_size = num_channels * 4
                image_stride = (xmax - xmin + 1)*pixel_size
                
                if self.fast_mode:
                    self.buffer = np.array([(0.0, 0.0, 0.0, 0.0)] * ((xmax+1) * (ymax+1))).reshape(ymax + 1,xmax +1, 4)
                    self.result = self.engine.begin_result(0, 0, xmax, ymax)
                    
                self.ymax = ymax
                self.xmax = xmax
                self.num_channels = num_channels
                self.pixel_size = pixel_size
                is_ready = True

                # send that we're ready
                client_writer.write(struct.pack("I", 0))
            else:
                #print('receive')
                data = (await client_reader.read(2))
                cmd, other = struct.unpack("!bb", data)

                #if self.fast_mode and time.time() - last_update > 1:
                    #self.result.layers[0].passes[0].rect = reversed(self.buffer, self.xmax, self.ymax)
                    #self.engine.update_result(self.result)
                    #last_update = time.time()
                if cmd == IMAGE_DATA:
                    data = (await client_reader.readexactly(16))
                    w_xmin, w_xmax, w_ymin, w_ymax = struct.unpack("!IIII", data)
                    num_pixels = (w_xmax - w_xmin + 1)*(w_ymax - w_ymin + 1)
                    buffer_size = num_pixels*pixel_size
                    pixels = (await client_reader.readexactly(buffer_size))
                    loop.run_in_executor(self.executor, self.process_bucket, w_xmin, w_xmax, w_ymin, w_ymax, pixels)

                elif cmd == IMAGE_END:
                    display_done = True
                    return

    def start(self, loop):
        """
        Starts the TCP server, so that it listens on port 12345.

        For each client that connects, the accept_client method gets
        called.  This method runs the loop until the server sockets
        are ready to accept connections.
        """
        print('starting server')
        self.server = loop.run_until_complete(
            asyncio.streams.start_server(self._accept_client,
                                         '127.0.0.1', self.port,
                                         loop=loop))

    def stop(self, loop):
        """
        Stops the TCP server, i.e. closes the listening socket(s).

        This method runs the loop until the server sockets are closed.
        """
        if self.server is not None:
            self.executor.shutdown(wait=True)
            print('process time ', self.process_time)
            self.server.close()
            loop.run_until_complete(self.server.wait_closed())
            if self.fast_mode:
                self.result.layers[0].passes[0].rect = reversed(self.buffer, self.xmax, self.ymax)
                self.engine.update_result(self.result)
                self.engine.end_result(self.result)
            self.server = None


