from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import torch
import wave
import io
import numpy as np
import tempfile
import logging
import os
from transformers import AutoModelForCausalLM, AutoTokenizer
from continue_tts.decoder import tokens_decoder_sync

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# TTS globals
model = None
tokenizer = None
model_loaded = False
SAMPLE_RATE = 24000
CHANNELS = 1
SAMPLE_WIDTH = 2

# ASR globals
asr_model = None
asr_loaded = False

def load_model():
    global model, tokenizer, model_loaded
    if model_loaded:
        return model
    try:
        logger.info("Loading Continue-TTS raw transformers model...")
        model_name = "SVECTOR-CORPORATION/Continue-TTS"
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            dtype=torch.float16,
            device_map="auto",
            trust_remote_code=True
        )
        model_loaded = True
        logger.info("✅ Raw model loaded successfully!")
        return model
    except Exception as e:
        logger.error(f"❌ Failed to load model: {e}")
        raise

def _format_prompt(prompt, voice="nova", tokenizer=None):
    adapted_prompt = f"{voice}: {prompt}"
    prompt_tokens = tokenizer(adapted_prompt, return_tensors="pt")
    start_token = torch.tensor([[128259]], dtype=torch.int64)
    end_tokens = torch.tensor([[128009, 128260, 128261, 128257]], dtype=torch.int64)
    all_input_ids = torch.cat([start_token, prompt_tokens.input_ids, end_tokens], dim=1)
    return all_input_ids

def load_asr_model():
    global asr_model, asr_loaded
    if asr_loaded:
        return asr_model
    try:
        logger.info("Loading Qwen3-ASR-1.7B model...")
        from qwen_asr import Qwen3ASRModel
        asr_model = Qwen3ASRModel.from_pretrained(
            "Qwen/Qwen3-ASR-1.7B",
            dtype=torch.bfloat16,
            device_map="cuda:0" if torch.cuda.is_available() else "cpu",
            max_new_tokens=512,
        )
        asr_loaded = True
        logger.info("✅ ASR model loaded successfully!")
        return asr_model
    except Exception as e:
        logger.error(f"❌ Failed to load ASR model: {e}")
        raise

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'healthy',
        'model_loaded': model_loaded,
        'asr_loaded': asr_loaded,
        'continue_tts_available': True,
        'asr_available': True,
        'sample_rate': SAMPLE_RATE,
        'channels': CHANNELS,
        'sample_width_bytes': SAMPLE_WIDTH,
    })

@app.route('/tts/generate', methods=['POST'])
def generate_speech():
    try:
        if not request.is_json:
            return jsonify({'error': 'Unsupported media type. Use Content-Type: application/json'}), 415

        data = request.get_json(silent=True)
        text = data.get('text')
        voice = data.get('voice', 'nova')
        
        if not text:
            return jsonify({'error': 'Missing text'}), 400
            
        if not model_loaded:
            load_model()
            
        # Format prompt according to model expectations
        input_ids = _format_prompt(text, voice, tokenizer).to(model.device)
        
        # Generation without vLLM
        with torch.no_grad():
            outputs = model.generate(
                input_ids,
                max_new_tokens=1200,
                temperature=0.6,
                top_p=0.8,
                repetition_penalty=1.3,
                pad_token_id=tokenizer.eos_token_id
            )
            
        new_ids = outputs[0][input_ids.shape[1]:]
        
        def token_generator():
            for token_id in new_ids:
                yield tokenizer.decode(token_id)
                
        # Use Continue-TTS sync decoder
        audio_chunks = list(tokens_decoder_sync(token_generator()))
        
        if not audio_chunks:
            return jsonify({'error': 'Decoding produced no audio chunks'}), 500
            
        pcm_bytes = b''.join(audio_chunks)

        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(SAMPLE_WIDTH)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(pcm_bytes)
        
        wav_buffer.seek(0)
        return send_file(wav_buffer, mimetype='audio/wav', as_attachment=False, download_name='speech.wav')

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/tts/test', methods=['GET'])
def test_tts():
    return send_file(io.BytesIO(b'RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00'), mimetype='audio/wav')

@app.route('/asr/transcribe', methods=['POST'])
def transcribe_audio():
    try:
        if 'audio' not in request.files:
            return jsonify({'error': 'No audio file provided. Send as multipart form with key "audio"'}), 400

        audio_file = request.files['audio']
        language = request.form.get('language', None)  # Optional: "English", "Chinese", etc.

        # Save to temp file for processing
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            audio_file.save(tmp.name)
            tmp_path = tmp.name

        try:
            if not asr_loaded:
                load_asr_model()

            results = asr_model.transcribe(
                audio=tmp_path,
                language=language,
            )

            if not results:
                return jsonify({'error': 'No transcription produced'}), 500

            return jsonify({
                'text': results[0].text,
                'language': results[0].language,
            })
        finally:
            os.unlink(tmp_path)

    except Exception as e:
        logger.error(f"ASR Error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
