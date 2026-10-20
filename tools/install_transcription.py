"""Install the upstream pretrained Basic Pitch model and its supported ONNX path.

Only the model wheel uses --no-deps: upstream metadata requires TensorFlow on
Python 3.12 although ONNX inference does not import or use TensorFlow. See the
comment in requirements-transcription.txt. No model weights are downloaded from
an unofficial source. pip retains its normal HTTPS and artifact verification.
"""
from pathlib import Path
import subprocess
import sys
root = Path(__file__).resolve().parents[1]
constraints=['-c',str(root/'requirements-cloud.lock')] if sys.platform.startswith('linux') and (root/'requirements-cloud.lock').is_file() else []
subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', str(root/'requirements-transcription.txt'),*constraints], check=True)
subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-deps', 'basic-pitch==0.4.0'], check=True)
from basic_pitch.inference import Model
from basic_pitch import build_icassp_2022_model_path, FilenameSuffix
path = build_icassp_2022_model_path(FilenameSuffix.onnx)
model = Model(path)
print('Verified installed Basic Pitch ONNX model:', path.name, model.model_type)
