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


def reversed(buffer, width, height):
    return np.flipud(buffer).reshape((width + 1) * (height + 1), 4)


class DisplayServer:
    """
    This is just an example of how a TCP server might be potentially
    structured.  This class has basically 3 methods: start the server,
    handle a client, and stop the server.

    Note that you don't have to follow this structure, it is really
    just an example or possible starting point.
    """

    def __init__(self, engine, port, prman):
        self.server = None  # encapsulates the server sockets
        self.engine = engine
        self.port = port
        # this keeps track of all the clients that connected to our
        # server.  It can be useful in some cases, for instance to
        # kill client connections or to broadcast some data to all
        # clients...
        self.clients = {}  # task -> (reader, writer)
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        self.reading = False
        self.process_status = None
        self.process_time = 0
        self.prman = prman
        self.buffer = []
        self.fast_mode = True
        self.done = False

    def _accept_client(self, client_reader, client_writer):
        """
        This method accepts a new client connection and creates a Task
        to handle this client.  self.clients is updated to keep track
        of the new client.
        """

        # start a new Task to handle this specific client connection
        task = asyncio.Task(self._handle_client(client_reader, client_writer))
        self.clients[task] = (client_reader, client_writer)

        def client_done(task):
            if len(self.clients) == 1:
                loop = asyncio.get_event_loop()
                loop.stop()
            del self.clients[task]

        task.add_done_callback(client_done)

    def draw_buffer(self):
        while not self.done:
            time.sleep(5.0)
            result = self.engine.begin_result(
                0, 0, self.xmax + 1, self.ymax + 1)
            result.layers[0].passes[0].rect = self.buffer
            self.engine.end_result(result)

    async def _handle_client(self, client_reader, client_writer):
        """
        This method actually does the work to handle the requests for
        a specific client.  The protocol is line oriented, so there is
        a main loop that reads a line with a request and then sends
        out one or more lines back to the client with the result.
        """
        sep = b';'
        is_ready = False
        loop = asyncio.get_event_loop()
        display_done = False

        last_update = time.time()
        while not display_done:
            if not is_ready:
                data = (await client_reader.read(1024)).split(sep)

                image_name = data[0].decode()[1:]
                dspy_params = data[2]

                xmin, xmax, ymin, ymax, a_len, z_len, channel_len, num_channels, merge = struct.unpack(
                    "!IIIIIIIIb", data[2][1:])
                pixel_size = int(a_len / 8) + int(z_len / 8) + \
                    int(channel_len / 8 * num_channels)  # bits ->bytes
                num_channels = num_channels + 1 if a_len > 0 else num_channels
                num_channels = num_channels + 1 if z_len > 0 else num_channels
                pixel_size = num_channels * 4
                image_stride = (xmax - xmin + 1) * pixel_size

                self.ymax = ymax
                self.xmax = xmax
                self.num_channels = num_channels
                self.pixel_size = pixel_size

                if self.fast_mode:
                    self.buffer = np.array(
                        [(0.0, 0.0, 0.0, 0.0)] * ((xmax + 1) * (ymax + 1)))
                    self.use_buffer = np.flipud(
                        self.buffer.reshape(ymax + 1, xmax + 1, 4))
                    buff_task = loop.run_in_executor(
                        self.executor, self.draw_buffer)

                is_ready = True

                # send that we're ready
                client_writer.write(struct.pack("I", 0))
            else:
                # print('receive')
                data = (await client_reader.read(2))
                cmd, other = struct.unpack("!bb", data)

                if cmd == IMAGE_DATA:
                    data = (await client_reader.readexactly(16))
                    w_xmin, w_xmax, w_ymin, w_ymax = struct.unpack(
                        "!IIII", data)
                    w_xmax += 1
                    w_ymax += 1
                    width = w_xmax - w_xmin
                    height = w_ymax - w_ymin

                    num_pixels = (w_xmax - w_xmin) * (w_ymax - w_ymin)
                    pixels = (await client_reader.readexactly(num_pixels * pixel_size))
                    self.use_buffer[w_ymin: w_ymax, w_xmin: w_xmax] = np.fromstring(
                        pixels, dtype="f", count=num_pixels * 4).reshape((height, width, 4))[:, :, [1, 2, 3, 0]]

                elif cmd == IMAGE_END:
                    #loop.run_in_executor(self.executor, self.process_bucket, -1, -1, -1, -1, "")
                    #self.done = True
                    return

    def start(self, loop):
        """
        Starts the TCP server, so that it listens on port 12345.

        For each client that connects, the accept_client method gets
        called.  This method runs the loop until the server sockets
        are ready to accept connections.
        """
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
            self.executor.shutdown(wait=False)
            self.server.close()
            loop.run_until_complete(self.server.wait_closed())
            if self.fast_mode:
                result = self.engine.begin_result(
                    0, 0, self.xmax + 1, self.ymax + 1)
                result.layers[0].passes[0].rect = self.buffer
                self.engine.end_result(result)
            self.server = None
