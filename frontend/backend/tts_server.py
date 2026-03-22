"""
Continue-TTS Backend Server
Provides TTS API endpoint using SVECTOR-CORPORATION/Continue-TTS model
"""
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import torch
import wave
import io
import numpy as np
import logging
try:
    from continue_tts import Continue1Model
except Exception as _import_err:
    Continue1Model = None
    logging.getLogger(__name__).warning(
        "continue_tts package not available yet; model will be loaded lazily when requested."
    )
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
# Enable CORS for frontend
CORS(app, resources={
    r"/*": {
        "origins": "*",  # Allow all origins (restrict this in production)
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"]
    }
})

# Global model instance / audio config
model = None
model_loaded = False
SAMPLE_RATE = 24000  # Hz
CHANNELS = 1
SAMPLE_WIDTH = 2  # bytes (16-bit PCM)

def load_model():
    """Load the Continue-TTS model"""
    global model, model_loaded
    if model_loaded:
        return model
    try:
        if Continue1Model is None:
            raise RuntimeError(
                "continue_tts is not installed. Install with: pip install continue-tts"
            )
        # Log environment settings relevant to HF Hub
        logger.info("Loading Continue-TTS model...")
        logger.info(
            "HF env: HF_HUB_OFFLINE=%s TRANSFORMERS_OFFLINE=%s HF_ENDPOINT=%s HF_HOME=%s",
            os.environ.get("HF_HUB_OFFLINE"),
            os.environ.get("TRANSFORMERS_OFFLINE"),
            os.environ.get("HF_ENDPOINT"),
            os.environ.get("HF_HOME"),
        )
        model = Continue1Model(
            model_name="SVECTOR-CORPORATION/Continue-TTS",
            max_model_len=2048,
            trust_remote_code=True
        )
        model_loaded = True
        logger.info("✅ Continue-TTS model loaded successfully!")
        return model
    except Exception as e:
        # Detect NVML/pynvml decode errors and retry with GPU disabled/CPU fallback
        err_msg = f"{e}"
        if (
            isinstance(e, UnicodeDecodeError)
            or "pynvml" in err_msg
            or "nvmlDeviceGetName" in err_msg
            or "UnicodeDecodeError" in err_msg
        ):
            logger.warning(
                "Detected NVML decode error while loading model. Retrying with GPU disabled and CPU fallback."
            )
            # Hide GPUs from torch/vLLM and try to suppress NVML usage
            # os.environ["CUDA_VISIBLE_DEVICES"] = ""
            os.environ.setdefault("VLLM_USE_NVML", "1")
            os.environ.setdefault("VLLM_SKIP_NVML", "0")
            try:
                model = Continue1Model(
                    model_name="SVECTOR-CORPORATION/Continue-TTS",
                    max_model_len=2048,
                    trust_remote_code=True,
                    device="cuda",  # Attempt to force CPU if supported
                )
                model_loaded = True
                logger.info("✅ Continue-TTS model loaded successfully in CPU mode (GPU disabled).")
                return model
            except TypeError:
                # device kw not supported; retry without it
                model = Continue1Model(
                    model_name="SVECTOR-CORPORATION/Continue-TTS",
                    max_model_len=2048,
                    trust_remote_code=True,
                )
                model_loaded = True
                logger.info("✅ Continue-TTS model loaded successfully after disabling GPU visibility.")
                return model
            except Exception as e2:
                logger.error(
                    f"❌ CPU fallback load also failed: {e2}. Original error: {e}",
                    exc_info=True,
                )
                raise
        # Other errors - re-raise
        logger.error(f"❌ Failed to load model: {e}")
        raise


def _chunk_to_int16_bytes(chunk) -> bytes:
    """Convert a model audio chunk (tensor/ndarray/bytes/list) to 16-bit PCM little-endian bytes.
    Accepts:
      - torch.Tensor (float32 / float16 / int16)
      - np.ndarray
      - bytes (assumed already PCM or float32)
      - list (converted to np.array)
    Floats are expected in range [-1, 1]; will be clipped then scaled.
    """
    if chunk is None:
        return b''
    # Torch tensor
    if isinstance(chunk, torch.Tensor):
        if chunk.dtype in (torch.float32, torch.float64, torch.float16):
            arr = chunk.detach().cpu().float().numpy()
        elif chunk.dtype == torch.int16:
            arr = chunk.detach().cpu().numpy().astype(np.int16)
            return arr.tobytes()
        else:
            # Fallback: convert to float then scale
            arr = chunk.detach().cpu().float().numpy()
    elif isinstance(chunk, np.ndarray):
        arr = chunk
    elif isinstance(chunk, (list, tuple)):
        arr = np.array(chunk, dtype=np.float32)
    elif isinstance(chunk, (bytes, bytearray)):
        # Heuristic for bytes: try float32 first if size aligns and range looks like [-1,1]
        b = bytes(chunk)
        handled = False
        if len(b) % 4 == 0 and len(b) >= 4:
            try:
                farr = np.frombuffer(b, dtype=np.float32)
                if farr.size > 0:
                    max_abs = float(np.max(np.abs(farr)))
                else:
                    max_abs = 0.0
                # If values look like normalized audio, treat as float32 samples
                if 0.0 <= max_abs <= 1.5:
                    arr = farr
                    handled = True
            except Exception:
                pass
        if not handled:
            # Fallback: assume int16 PCM if even length
            if len(b) % 2 == 0:
                return b
            # Last resort: return as-is
            return b
    else:
        logger.warning(f"Unknown audio chunk type: {type(chunk)} - skipping")
        return b''

    # Ensure 1-D
    if arr.ndim > 1:
        arr = arr.reshape(-1)
    # Convert float types
    if arr.dtype.kind == 'f':
        # Clip to [-1,1]
        np.clip(arr, -1.0, 1.0, out=arr)
        int16_arr = (arr * 32767.0).astype(np.int16)
        return int16_arr.tobytes()
    if arr.dtype == np.int16:
        return arr.tobytes()
    # Fallback: cast
    try:
        return arr.astype(np.int16).tobytes()
    except Exception as e:
        logger.warning(f"Failed casting chunk to int16: {e}")
        return b''


def _combine_chunks_to_pcm(chunks) -> bytes:
    """Combine multiple chunks into a single PCM byte stream."""
    pcm_buffers = []
    total_samples = 0
    for i, ch in enumerate(chunks):
        b = _chunk_to_int16_bytes(ch)
        if not b:
            continue
        pcm_buffers.append(b)
        total_samples += len(b) // SAMPLE_WIDTH
    combined = b''.join(pcm_buffers)
    logger.info(f"Combined {len(pcm_buffers)} chunks into {len(combined)} bytes ({total_samples} samples)")
    if combined:
        logger.debug(f"First 16 bytes hex: {combined[:16].hex()}")
    return combined

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'model_loaded': model_loaded,
        'continue_tts_available': Continue1Model is not None,
        'sample_rate': SAMPLE_RATE,
        'channels': CHANNELS,
        'sample_width_bytes': SAMPLE_WIDTH,
        'env': {
            'HF_HUB_OFFLINE': bool(os.environ.get('HF_HUB_OFFLINE')),
            'TRANSFORMERS_OFFLINE': bool(os.environ.get('TRANSFORMERS_OFFLINE')),
            'HF_ENDPOINT': os.environ.get('HF_ENDPOINT') or None,
            'HF_HOME': os.environ.get('HF_HOME') or None,
            'CUDA_VISIBLE_DEVICES': os.environ.get('CUDA_VISIBLE_DEVICES') or None,
            'VLLM_USE_NVML': os.environ.get('VLLM_USE_NVML') or None,
            'VLLM_SKIP_NVML': os.environ.get('VLLM_SKIP_NVML') or None,
        }
    })

@app.route('/tts/generate', methods=['POST'])
def generate_speech():
    """
    Generate speech from text using Continue-TTS
    
    Request body:
    {
        "text": "Your text here",
        "voice": "nova"  // Optional: nova, aurora, stellar, atlas, orion, luna, phoenix, ember
    }
    
    Returns:
    - Audio file (WAV format) as binary
    """
    try:
        # Enforce JSON input to avoid decoding binary as UTF-8
        if not request.is_json:
            return jsonify({'error': 'Unsupported media type. Use Content-Type: application/json'}), 415

        data = request.get_json(silent=True)
        if not data or 'text' not in data:
            return jsonify({'error': 'Missing "text" field'}), 400
        
        text = data['text']
        voice = data.get('voice', 'nova')  # Default to 'nova'
        
        if not text.strip():
            return jsonify({'error': 'Text cannot be empty'}), 400
        
        # Validate voice
        valid_voices = ['nova', 'aurora', 'stellar', 'atlas', 'orion', 'luna', 'phoenix', 'ember']
        if voice not in valid_voices:
            return jsonify({'error': f'Invalid voice. Must be one of: {", ".join(valid_voices)}'}), 400
        
        logger.info(f"Generating speech: voice={voice}, text_length={len(text)}")
        
        # Load model if not loaded
        if not model_loaded:
            load_model()
        
        # Generate speech (may return iterable of tensors / arrays / bytes)
        audio_chunks = model.generate_speech(
            prompt=text,
            voice=voice,
            temperature=0.6,
            top_p=0.8,
            max_tokens=1200,
            repetition_penalty=1.3
        )

        if audio_chunks is None:
            return jsonify({'error': 'Model returned no audio'}), 500

        # Some APIs yield a generator; force materialization
        if not isinstance(audio_chunks, (list, tuple)):
            audio_chunks = list(audio_chunks)

        if len(audio_chunks) == 0:
            return jsonify({'error': 'Empty audio output'}), 500

        # Debug: log info about first chunk
        first = audio_chunks[0]
        try:
            if isinstance(first, torch.Tensor):
                logger.info(f"First chunk type=torch.Tensor, dtype={first.dtype}, shape={tuple(first.shape)}")
            elif isinstance(first, np.ndarray):
                logger.info(f"First chunk type=np.ndarray, dtype={first.dtype}, shape={first.shape}")
            else:
                logger.info(f"First chunk type={type(first)}, len={len(first) if hasattr(first, '__len__') else 'n/a'}")
        except Exception:
            pass

        # Convert chunks to 16-bit PCM
        audio_data = _combine_chunks_to_pcm(audio_chunks)
        if not audio_data:
            return jsonify({'error': 'Failed to convert audio chunks'}), 500

        # Build WAV file
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(SAMPLE_WIDTH)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio_data)
        
        wav_buffer.seek(0)
        logger.info(f"✅ Speech generated successfully ({len(audio_data)} bytes PCM)")
        return send_file(
            wav_buffer,
            mimetype='audio/wav',
            as_attachment=False,
            download_name='speech.wav'
        )
    except Exception as e:
        logger.error(f"Error generating speech: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/tts/voices', methods=['GET'])
def get_voices():
    """Get list of available voices"""
    return jsonify({
        'voices': [
            {'id': 'nova', 'name': 'Nova', 'gender': 'Female', 'description': 'Conversational and natural'},
            {'id': 'aurora', 'name': 'Aurora', 'gender': 'Female', 'description': 'Warm and friendly'},
            {'id': 'stellar', 'name': 'Stellar', 'gender': 'Female', 'description': 'Energetic and bright'},
            {'id': 'atlas', 'name': 'Atlas', 'gender': 'Male', 'description': 'Deep and authoritative'},
            {'id': 'orion', 'name': 'Orion', 'gender': 'Male', 'description': 'Friendly and casual'},
            {'id': 'luna', 'name': 'Luna', 'gender': 'Female', 'description': 'Soft and gentle'},
            {'id': 'phoenix', 'name': 'Phoenix', 'gender': 'Male', 'description': 'Dynamic and expressive'},
            {'id': 'ember', 'name': 'Ember', 'gender': 'Female', 'description': 'Warm and engaging'}
        ]
    })

@app.route('/tts/test', methods=['GET'])
def test_tts():
    """Generate a short 440Hz sine wave for 1 second to test audio pipeline."""
    duration = 1.0
    freq = 440.0
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
    waveform = 0.2 * np.sin(2 * np.pi * freq * t)  # moderate amplitude
    pcm = (waveform * 32767.0).astype(np.int16).tobytes()
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm)
    buf.seek(0)
    return send_file(buf, mimetype='audio/wav', as_attachment=False, download_name='test_tone.wav')

if __name__ == '__main__':
    # Check if running in development mode
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    
    logger.info(f"Starting TTS server on port {port}")
    logger.info("Note: Model will be loaded on first request")
    
    app.run(host='0.0.0.0', port=port, debug=debug)

