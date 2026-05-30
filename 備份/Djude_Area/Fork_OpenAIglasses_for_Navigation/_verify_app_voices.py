"""一次性驗證腳本：跑完即可刪"""
import wave, os, json, struct

audio_dir = 'Android/assets/audio'
app_files = [f for f in os.listdir(audio_dir) if f.endswith('_App.wav')]
sr_dist = {}
amp_issues = []
for f in app_files:
    p = os.path.join(audio_dir, f)
    with wave.open(p, 'rb') as wf:
        sr = wf.getframerate()
        nf = wf.getnframes()
        frames = wf.readframes(nf)
        samples = struct.unpack(f'<{len(frames)//2}h', frames)
        max_amp = max(abs(s) for s in samples) if samples else 0
    sr_dist[sr] = sr_dist.get(sr, 0) + 1
    if max_amp >= 32760:
        amp_issues.append((f, max_amp))

print(f'_App.wav 總數: {len(app_files)}')
print(f'採樣率分布: {sr_dist}')
print(f'振幅 clipping (>= 32760): {len(amp_issues)}')
for f, m in amp_issues[:5]:
    print(f'  {f}: {m}')

print()
with open('Android/assets/voice_map.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
referenced = set(v['file'] for v in data.values() if 'file' in v)
app_refs = [v for v in referenced if v.endswith('_App.wav')]
old_refs = [v for v in referenced if not v.endswith('_App.wav')]
print(f'voice_map 總引用: {len(referenced)}')
print(f'  指向 _App.wav: {len(app_refs)}')
print(f'  指向舊 8kHz: {len(old_refs)}')
for k, v in data.items():
    if not v['file'].endswith('_App.wav'):
        print(f'  [LEFT] {k}: {v["file"]}')
