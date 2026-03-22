# Continue-TTS Backend Server

This backend provides a REST API for the Continue-TTS model from Hugging Face.

## Setup

1. **Install Python dependencies:**
```bash
cd backend
pip install -r requirements.txt
```

2. **Install Continue-TTS package:**
```bash
pip install continue-speech
```

3. **Run the server:**
```bash
python tts_server.py
```

The server will start on `http://localhost:5000`

## API Endpoints

### `GET /health`
Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "model_loaded": true
}
```

### `POST /tts/generate`
Generate speech from text.

**Request:**
```json
{
  "text": "Hello, this is a test message.",
  "voice": "nova"
}
```

**Response:** Audio file (WAV format, 24kHz, mono)

**Available voices:**
- `nova` (Female) - Conversational and natural
- `aurora` (Female) - Warm and friendly
- `stellar` (Female) - Energetic and bright
- `atlas` (Male) - Deep and authoritative
- `orion` (Male) - Friendly and casual
- `luna` (Female) - Soft and gentle
- `phoenix` (Male) - Dynamic and expressive
- `ember` (Female) - Warm and engaging

### `GET /tts/voices`
Get list of available voices.

**Response:**
```json
{
  "voices": [
    {
      "id": "nova",
      "name": "Nova",
      "gender": "Female",
      "description": "Conversational and natural"
    },
    ...
  ]
}
```

## Environment Variables

- `PORT` - Server port (default: 5000)
- `DEBUG` - Enable debug mode (default: False)

## Requirements

- Python 3.8+
- GPU recommended for real-time generation (~7GB VRAM for FP16)
- ~14GB VRAM for FP32

## Notes

- The model is loaded on first request (lazy loading)
- First request may take longer as the model downloads and loads
- Subsequent requests will be faster
- For production, consider pre-loading the model at startup

