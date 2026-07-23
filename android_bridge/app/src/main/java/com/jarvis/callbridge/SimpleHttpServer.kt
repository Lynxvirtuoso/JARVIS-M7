package com.jarvis.callbridge

import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStream
import java.net.ServerSocket
import java.net.Socket
import kotlin.concurrent.thread

class SimpleHttpServer(
    private val port: Int, 
    private val tokenProvider: () -> String, 
    private val onDial: (String) -> Unit
) {
    private var serverSocket: ServerSocket? = null
    private var running = false

    fun start() {
        running = true
        serverSocket = ServerSocket(port)
        thread(start = true, isDaemon = true) {
            while (running) {
                try {
                    val socket = serverSocket?.accept()
                    if (socket != null) {
                        handleClient(socket)
                    }
                } catch (e: Exception) {
                    // Server stopped or socket error
                }
            }
        }
    }

    fun stop() {
        running = false
        serverSocket?.close()
    }

    private fun handleClient(socket: Socket) {
        thread(start = true, isDaemon = true) {
            try {
                val reader = BufferedReader(InputStreamReader(socket.inputStream))
                val firstLine = reader.readLine() ?: ""
                
                // Parse GET /dial?number=X&token=Y HTTP/1.1
                if (firstLine.startsWith("GET ")) {
                    val url = firstLine.split(" ")[1]
                    val path = url.substringBefore("?")
                    val query = url.substringAfter("?", "")
                    val params = parseQuery(query)

                    val number = params["number"]
                    val requestToken = params["token"]
                    val configuredToken = tokenProvider()

                    val outputStream = socket.getOutputStream()
                    if (path == "/dial") {
                        if (configuredToken.isEmpty()) {
                            sendResponse(outputStream, 500, "Internal Server Error", "Security token is not configured on the phone.")
                        } else if (requestToken == configuredToken) {
                            if (!number.isNullOrEmpty()) {
                                onDial(number)
                                sendResponse(outputStream, 200, "OK", "Dialing initiated for $number")
                            } else {
                                sendResponse(outputStream, 400, "Bad Request", "Missing 'number' parameter")
                            }
                        } else {
                            sendResponse(outputStream, 403, "Forbidden", "Invalid token")
                        }
                    } else if (path == "/health") {
                        sendResponse(outputStream, 200, "OK", "Healthy")
                    } else {
                        sendResponse(outputStream, 404, "Not Found", "Endpoint not found")
                    }
                }
            } catch (e: Exception) {
                e.printStackTrace()
            } finally {
                socket.close()
            }
        }
    }

    private fun parseQuery(query: String): Map<String, String> {
        val params = mutableMapOf<String, String>()
        if (query.isNotEmpty()) {
            val pairs = query.split("&")
            for (pair in pairs) {
                val idx = pair.indexOf("=")
                if (idx > 0) {
                    val key = pair.substring(0, idx)
                    val value = pair.substring(idx + 1)
                    params[key] = java.net.URLDecoder.decode(value, "UTF-8")
                }
            }
        }
        return params
    }

    private fun sendResponse(out: OutputStream, statusCode: Int, statusText: String, body: String) {
        val responseBytes = body.toByteArray()
        val header = "HTTP/1.1 $statusCode $statusText\r\n" +
                "Content-Type: text/plain\r\n" +
                "Content-Length: ${responseBytes.size}\r\n" +
                "Connection: close\r\n\r\n"
        out.write(header.toByteArray())
        out.write(responseBytes)
        out.flush()
    }
}
