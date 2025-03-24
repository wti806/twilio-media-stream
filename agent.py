import asyncio
import json
import base64
import audioop
import websockets
from quart import websocket

class AudioProxy:
    def __init__(self):
        self.target_ws_url = "wss://vz-live-agent-backend-uzfjfm4moq-uc.a.run.app"
        self.target_websocket = None
        self.stream_sid = None
        self.twilio_ws = None

    async def twilio_audio_stream(self):
        """
        Receive messages from the Twilio (Quart) websocket in a while-True loop.
        """
        self.twilio_ws = websocket

        while True:
            try:
                # If the client disconnects, this receive can raise an exception.
                message = await self.twilio_ws.receive()

                # If you get an empty message, treat it as a closed connection:
                if not message:
                    print("No more messages from Twilio WebSocket (empty). Closing.")
                    break

                data = json.loads(message)

                if data['event'] == 'start':
                    self.stream_sid = data['start']['streamSid']
                    print(f"Stream started - {self.stream_sid}")

                elif data['event'] == 'media':
                    # Base64 encoded u-law from Twilio
                    audio_data = data['media']['payload']
                    decoded_audio = base64.b64decode(audio_data)
                    # Convert Twilio's u-law to PCM
                    pcm_audio = audioop.ulaw2lin(decoded_audio, 2)

                    # Forward to target if connected:
                    await self.send_audio_to_target(pcm_audio)

                elif data['event'] == 'stop':
                    print("Stream stopped by Twilio.")
                    break

            except websockets.exceptions.ConnectionClosed:
                print("Twilio WebSocket connection unexpectedly closed (websockets.exceptions).")
                break
            except Exception as e:
                print(f"Error in twilio_audio_stream: {e}")
                break

        # After the loop ends (Twilio closed or error occurred), close target.
        await self.close_target_connection()

    async def send_audio_to_target(self, pcm_audio: bytes):
        """
        Sends PCM audio to the target WebSocket server.
        We do a try/except around ConnectionClosed rather than checking `.open` or `.closed`.
        """
        if self.target_websocket is not None:
            try:
                message = {
                    "type": "audio",
                    "data": base64.b64encode(pcm_audio).decode('utf-8')
                }
                await self.target_websocket.send(json.dumps(message))
            except websockets.exceptions.ConnectionClosed:
                print("Target WebSocket connection closed while sending audio.")
                await self.close_all_connections()
            except Exception as e:
                print(f"Error sending audio to target: {e}")
                await self.close_all_connections()

    def convert_audio_to_mulaw(self, audio_data: bytes) -> str:
        """
        Convert raw PCM audio (24k) to mu-law (8k), return base64 string.
        """
        data_8k, _ = audioop.ratecv(audio_data, 2, 1, 24000, 8000, None)
        mulaw_8k = audioop.lin2ulaw(data_8k, 2)
        encoded_audio = base64.b64encode(mulaw_8k).decode('utf-8')
        return encoded_audio

    async def proxy_responses(self):
        """
        Reads from the target websocket and relays to Twilio.
        """
        if self.target_websocket is None:
            return

        try:
            async for message in self.target_websocket:
                print(f"Received from target: {message}")

                # Try to parse JSON
                if isinstance(message, str):
                    try:
                        target_data = json.loads(message)

                        # If it’s audio, convert to mulaw and send to Twilio
                        if target_data.get("type") == "audio":
                            decoded_audio = base64.b64decode(target_data["data"])
                            mulaw_audio = self.convert_audio_to_mulaw(decoded_audio)
                            response_to_twilio = {
                                "event": "media",
                                "streamSid": self.stream_sid,
                                "media": {
                                    "payload": mulaw_audio
                                }
                            }
                            # Send to Twilio (if still connected)
                            try:
                                if self.twilio_ws:
                                    await self.twilio_ws.send(json.dumps(response_to_twilio))
                            except Exception as e:
                                print(f"Error sending audio to Twilio: {e}")

                        else:
                            # Possibly forward other messages to Twilio
                            try:
                                if self.twilio_ws:
                                    await self.twilio_ws.send(message)
                            except Exception as e:
                                print(f"Error forwarding to Twilio: {e}")

                    except json.JSONDecodeError:
                        print(f"Non-JSON message from target: {message}")

                elif isinstance(message, bytes):
                    # Handle binary if needed
                    pass

        except websockets.exceptions.ConnectionClosed:
            print("Target WebSocket connection closed while receiving responses.")
            await self.close_twilio_connection()
        except Exception as e:
            print(f"Error receiving or proxying responses from target: {e}")
            await self.close_twilio_connection()

    async def websocket(self):
        """
        1. Connect to the target WebSocket.
        2. Run both twilio_audio_stream (reading from Twilio) and proxy_responses (reading from target).
        """
        print(f"Connecting to target WebSocket: {self.target_ws_url}")
        try:
            async with websockets.connect(self.target_ws_url) as ws:
                self.target_websocket = ws
                print("Connected to target WebSocket.")

                # Run both tasks concurrently
                await asyncio.gather(
                    self.twilio_audio_stream(),
                    self.proxy_responses(),
                )

                print('Proxy tasks completed.')

        except ConnectionRefusedError:
            print(f"Connection refused to target WebSocket: {self.target_ws_url}")
            await self.close_twilio_connection()
        except Exception as e:
            print(f'Unexpected error in gemini_websocket (proxy): {e}')
            await self.close_all_connections()
        finally:
            # Ensure connections are closed
            await self.close_target_connection()

    async def close_target_connection(self):
        """Close target WebSocket if it’s still open."""
        if self.target_websocket is not None:
            try:
                await self.target_websocket.close()
            except Exception as e:
                print(f"Error closing target websocket: {e}")
        self.target_websocket = None

    async def close_twilio_connection(self):
        """Close Twilio WebSocket if needed (Quart)."""
        if self.twilio_ws is not None:
            print("Closing Twilio WebSocket connection.")
            try:
                await self.twilio_ws.close(1000)
            except Exception as e:
                print(f"Error closing Twilio connection: {e}")
        self.twilio_ws = None

    async def close_all_connections(self):
        """Close both Twilio and target websockets."""
        await self.close_twilio_connection()
        await self.close_target_connection()
