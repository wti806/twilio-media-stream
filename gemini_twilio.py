# gemini_twilio.py

from google import genai
from quart import websocket
import json
import base64
import audioop 

class GeminiTwilio:
    def __init__(self):
        # Initialize the Google Cloud GenAI SDK: https://googleapis.github.io/python-genai/#create-a-client
        self.client = genai.Client(vertexai=True, project='df-integration-demo', location='us-central1')

        # Set the model_id and config. System instructions and functions can be added to the config for more complex use cases
        self.model_id = "gemini-2.0-flash-exp"
        self.config = {"response_modalities": ["AUDIO"]}
        
        # This will hold the StreamSid sent from Twilio
        self.stream_sid = None # used 


    async def twilio_audio_stream(self):
        '''
        Async method to handle the incoming Twilio media stream: https://www.twilio.com/docs/voice/media-streams
        Messages come in as JSON strings review the "event" key and handle the events: https://www.twilio.com/docs/voice/media-streams/websocket-messages

        Start Event - extract the StreamSid and set self.stream_sid
        Media Event - Convert from mulaw to PCM audio and yield the resulting data
        Stop Event - print stream stopped
        '''
        while True:
            message = await websocket.receive()
            data = json.loads(message)
            if data['event'] == 'start':
                self.stream_sid = data['start']['streamSid']
                print(f"Stream started - {self.stream_sid}")
            elif data['event'] == 'media':
                audio_data = data['media']['payload'] # Base64 encoded audio
                decoded_audio = base64.b64decode(audio_data) # Decode the audio
                pcm_audio = audioop.ulaw2lin(decoded_audio, 2) # Convert to PCM
                yield pcm_audio
            elif data['event'] == 'stop':
                print("Stream stopped")


    def convert_audio_to_mulaw(self, audio_data: bytes) -> str:
        '''
        Converts audio bytes to mulaw and returns a base64 string
        Args:
            audio_data: (bytes) - the raw pcm audio data
        '''
        data, _ = audioop.ratecv(audio_data, 2, 1, 24000, 8000, None) # Convert from 24000 sample rate to 8000
        mulaw_audio = audioop.lin2ulaw(data, 2) # Convert to mulaw
        encoded_audio = base64.b64encode(mulaw_audio).decode('utf-8') # Convert to base64 encoded string
        return encoded_audio 


    async def gemini_websocket(self):
        '''
        Establishes a session (genai.types.AsyncSession) and starts a stream to process incoming audio and handle responses from Gemini
        '''
        print("New websocket connection established")
        async with self.client.aio.live.connect(model=self.model_id, config=self.config) as session:
            try:
                async for response in session.start_stream(stream=self.twilio_audio_stream(), mime_type='audio/pcm'):
                    if data := response.data:
                        message = {
                            "event": "media",
                            "streamSid": self.stream_sid,
                            "media": {
                                "payload": self.convert_audio_to_mulaw(data)
                            }
                        }
                        print(message)
                        await websocket.send(json.dumps(message))
            except Exception as e:
                print(f'Unexpected error in gemini_websocket: {e}')
            finally:
                print('Closing session')
                await websocket.close(code=200)
                await session.close()
