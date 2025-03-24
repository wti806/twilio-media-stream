from quart import Quart, websocket
from agent import AudioProxy
import os

app = Quart(__name__)

@app.websocket('/gemini')
async def talk_to_gemini():
    # await GeminiTwilio().gemini_websocket()
    await AudioProxy().websocket()

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)