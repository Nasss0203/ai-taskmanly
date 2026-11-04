"""Generate the isolated Colab teacher pilot; never train or replace v1 data."""
import json
from pathlib import Path
from textwrap import dedent

OUTPUT = Path(__file__).with_name("colab_pilot_v2.ipynb")


def build():
    cells = []

    def md(text):
        cells.append({"cell_type": "markdown", "metadata": {}, "source": dedent(text).strip().splitlines(True)})

    def code(text):
        cells.append({"cell_type": "code", "metadata": {}, "execution_count": None,
                      "outputs": [], "source": dedent(text).strip().splitlines(True)})

    md('''
    # Taskmanly AI — teacher pilot v2, 100 yêu cầu

    **Notebook này chỉ tạo/kiểm tra nhãn teacher. Không train LoRA, không xuất GGUF.**
    Mục tiêu dài hạn dự kiến: 2.000 yêu cầu train + 250 dev + 250 holdout; chưa sinh cả bộ ở đây.

    1. Dùng đúng tài khoản Google chứa bundle. Chọn Runtime → Change runtime type → GPU (T4 nếu có).
    2. Đặt `pilot-teacher-bundle.zip` vào `MyDrive/taskmanly-train/v2-20261104/pilot/`.
    3. Chạy từng ô theo thứ tự. Ô teacher mặc định tắt: chạy thử 5 câu, xem kết quả rồi mới chạy tiếp.
    4. Kết quả nằm trong `pilot/teacher-output/`, tách khỏi SFT/checkpoint cũ. Runtime ngắt thì chạy lại phần chuẩn bị để làm tiếp các câu chưa có log.

    Đây là 100 **đầu vào chưa có nhãn**, không phải 100 câu sạch đã đạt. Teacher có thể loại nhiều câu.
    Sau pilot phải đọc tay nhãn, kiểm toán tokenizer và chốt split trước khi cân nhắc train.
    ''')
    md("## 1. Kiểm tra GPU")
    code('''
    import subprocess, sys, os, json, time, hashlib, zipfile, shutil
    from pathlib import Path, PurePosixPath
    from collections import Counter
    from datetime import datetime, timezone
    import urllib.request

    gpu_info = subprocess.check_output(
        ['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader,nounits'], text=True)
    print(gpu_info)
    gpu_memory_mib = int(gpu_info.strip().splitlines()[0].rsplit(',', 1)[1].strip())
    assert gpu_memory_mib >= 12000, 'GPU dưới 12 GB: dừng và xem lại cấu hình teacher, không chạy tiếp trên CPU.'
    ''')
    md("## 2. Kết nối Drive — tự chọn đúng tài khoản trong hộp thoại")
    code('''
    from google.colab import drive
    drive.mount('/content/drive')
    ''')
    md('''
    ## 3. Xác minh bundle và 100 đầu vào

    Nếu báo sai hash: dừng, tải lại đúng bundle đã bàn giao; không bỏ qua kiểm tra.
    Notebook dùng hash của bundle pilot cuối đã cân 60 VI / 40 EN và sửa kỳ vọng vị trí.
    ''')
    code('''
    DRIVE_DIR = Path('/content/drive/MyDrive/taskmanly-train/v2-20261104/pilot')
    BUNDLE = DRIVE_DIR / 'pilot-teacher-bundle.zip'
    WORK = Path('/content/taskmanly-pilot-v2-20261104')
    TEACHER_ENV = Path('/content/taskmanly-pilot-teacher-env')
    RESULT_DIR = DRIVE_DIR / 'teacher-output'
    SFT = RESULT_DIR / 'sft.jsonl'
    LOG = SFT.with_suffix('.log.jsonl')
    MODEL = 'qwen3:14b'
    NUM_CTX = 16384
    OLLAMA_URL = 'http://127.0.0.1:11435'
    EXPECTED_BUNDLE_SHA256 = 'df1621ef6a822e06d6c892d59382caa2185719195bf82bda7984f149621a9eb8'
    EXPECTED_REQUESTS_SHA256 = '5dc0c2e88f34c81d1f12428692d7227e05329a6171fcc211ee46d4928a3b9787'
    EXPECTED_TEACHER_SHA256 = 'e372699c333dbfd5bb08a897ff299bd743bb38ffd9823ad742dbfc13f0145adf'
    FILTER_VERSION = 'raw-labels-v1'

    def sha256(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    assert BUNDLE.is_file(), f'Chưa thấy {BUNDLE}. Kiểm tra tài khoản và thư mục Drive.'
    assert sha256(BUNDLE) == EXPECTED_BUNDLE_SHA256, 'Sai phiên bản bundle: tải lại file ZIP cuối, không chạy tiếp.'
    with zipfile.ZipFile(BUNDLE) as archive:
        assert archive.testzip() is None, 'ZIP bị hỏng.'
        for name in archive.namelist():
            path = PurePosixPath(name)
            assert not path.is_absolute() and '..' not in path.parts, 'ZIP có đường dẫn không hợp lệ.'
        WORK.mkdir(parents=True, exist_ok=True)
        archive.extractall(WORK)
    REQUESTS = WORK / 'training/data/requests.jsonl'
    assert sha256(REQUESTS) == EXPECTED_REQUESTS_SHA256
    assert sha256(WORK / 'training/teacher.py') == EXPECTED_TEACHER_SHA256
    requests = [json.loads(line) for line in REQUESTS.read_text(encoding='utf-8').splitlines() if line.strip()]
    by_id = {row['id']: row for row in requests}
    assert len(requests) == len(by_id) == 100
    assert Counter(row['lang'] for row in requests) == {'vi': 60, 'en': 40}
    assert Counter(row['kind'] for row in requests)['need_more_context'] == 20
    os.chdir(WORK)
    print('Đúng bundle, đúng bộ lọc mới, đủ 100 đầu vào.')
    print('Phân bố:', dict(Counter(row['kind'] for row in requests)))
    print('Output riêng:', RESULT_DIR)
    ''')
    md("## 4. Cài môi trường teacher riêng trong Colab")
    code('''
    subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', 'virtualenv'], check=True)
    if not (TEACHER_ENV / 'bin/python').exists():
        subprocess.run([sys.executable, '-m', 'virtualenv', '-q', str(TEACHER_ENV)], check=True)
    PYTHON = str(TEACHER_ENV / 'bin/python')
    subprocess.run([PYTHON, '-m', 'pip', 'install', '-q', '-r', str(WORK / 'training/requirements-teacher.txt')], check=True)
    subprocess.run([PYTHON, '-c',
        "from training.teacher import FILTER_VERSION; "
        "from app.modules.modification_planner.schemas.modification_planner_schema import ModificationPlannerRequest; "
        "import json; from pathlib import Path; "
        "assert FILTER_VERSION == 'raw-labels-v1'; "
        "rows=[json.loads(x) for x in Path('training/data/requests.jsonl').read_text(encoding='utf-8').splitlines()]; "
        "[ModificationPlannerRequest.model_validate(r['request']) for r in rows]; "
        "print('Import, filter version và schema 100 yêu cầu: OK')"], cwd=WORK, check=True)
    ''')
    md('''
    ## 5. Cài Ollama và mở server riêng trong runtime Colab

    Cài từ nguồn chính thức. Không đổi Ollama trên Windows. Dùng cổng 11435 và cache riêng trong runtime.
    Việc cài/tải model cần mạng và dung lượng runtime; chưa có lời gọi teacher ở ô này.
    ''')
    code('''
    if not shutil.which('ollama'):
        if not shutil.which('zstd'):
            subprocess.run(['apt-get', 'update', '-qq'], check=True)
            subprocess.run(['apt-get', 'install', '-y', '-qq', 'zstd'], check=True)
        installer = Path('/content/taskmanly-install-ollama.sh')
        urllib.request.urlretrieve('https://ollama.com/install.sh', installer)
        subprocess.run(['sh', str(installer)], check=True)

    OLLAMA_ENV = {**os.environ, 'OLLAMA_HOST': '127.0.0.1:11435',
        'OLLAMA_MODELS': '/content/taskmanly-pilot-ollama-models',
        'OLLAMA_FLASH_ATTENTION': '1', 'OLLAMA_KV_CACHE_TYPE': 'q8_0',
        'OLLAMA_NUM_PARALLEL': '1', 'OLLAMA_MAX_LOADED_MODELS': '1'}

    def api(path, payload=None, timeout=30):
        data = None if payload is None else json.dumps(payload).encode('utf-8')
        request = urllib.request.Request(OLLAMA_URL + path, data=data,
            headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)

    if 'ollama_process' not in globals() or ollama_process.poll() is not None:
        port_in_use = False
        try:
            api('/api/version', timeout=2)
            port_in_use = True
        except Exception:
            pass
        assert not port_in_use, 'Cổng 11435 đã có server ngoài phiên notebook này. Dừng để kiểm tra, không tự tắt tiến trình khác.'
        ollama_log = open('/content/taskmanly-pilot-ollama.log', 'a', encoding='utf-8')
        ollama_process = subprocess.Popen(['ollama', 'serve'], env=OLLAMA_ENV,
            stdout=ollama_log, stderr=subprocess.STDOUT)
    for _ in range(90):
        if ollama_process.poll() is not None:
            raise RuntimeError(Path('/content/taskmanly-pilot-ollama.log').read_text()[-5000:])
        try:
            server_version = api('/api/version', timeout=2)
            break
        except Exception:
            time.sleep(1)
    else:
        raise RuntimeError('Server chưa sẵn sàng; xem /content/taskmanly-pilot-ollama.log')
    print('Ollama server:', server_version)
    ''')
    md("## 6. Tải model thầy qwen3:14b và kiểm tra GPU bằng một câu ngắn")
    code('''
    subprocess.run(['ollama', 'pull', MODEL], env=OLLAMA_ENV, check=True)
    warmup = api('/api/chat', {'model': MODEL, 'stream': False, 'think': False,
        'messages': [{'role': 'user', 'content': 'Return a JSON object with ok=true.'}],
        'format': {'type': 'object', 'properties': {'ok': {'type': 'boolean'}}, 'required': ['ok']},
        'options': {'temperature': 0, 'num_ctx': NUM_CTX, 'num_predict': 64},
        'keep_alive': '10m'}, timeout=600)
    assert warmup.get('done_reason') != 'length', 'Câu kiểm tra ngắn bị cắt; dừng để xem lại runtime.'
    assert json.loads(warmup['message']['content']).get('ok') is True
    running = api('/api/ps')
    loaded = next((m for m in running.get('models', []) if m.get('name', '').split(':')[0] == 'qwen3'), None)
    assert loaded and loaded.get('size_vram', 0) > 0, 'Ollama chưa dùng GPU: dừng, không chạy teacher trên CPU.'
    print('Model đang chạy:', {k: loaded.get(k) for k in ('name', 'digest', 'size', 'size_vram', 'context_length')})
    subprocess.run(['ollama', 'ps'], env=OLLAMA_ENV, check=True)
    print('Có sử dụng GPU; xem PROCESSOR để biết có bị chia sang CPU không.')
    ''')
    md('''
    ## 7. Kiểm tra output và chuẩn bị chạy tiếp an toàn

    Nếu output/log không khớp hoặc khác phiên bản, notebook dừng; không tự xóa, sửa hay trộn SFT.
    Không thay model/param giữa các lần tiếp tục cùng output. Muốn thử cấu hình khác phải tạo run riêng.
    ''')
    code('''
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    model_tags = api('/api/tags')['models']
    teacher_tag = next(m for m in model_tags if m.get('name') in (MODEL, MODEL + ':latest'))
    identity = {'bundle_sha256': EXPECTED_BUNDLE_SHA256, 'requests_sha256': EXPECTED_REQUESTS_SHA256,
        'teacher_sha256': EXPECTED_TEACHER_SHA256, 'filter_version': FILTER_VERSION,
        'model': MODEL, 'model_digest': teacher_tag['digest'], 'num_ctx': NUM_CTX,
        'ollama_version': server_version['version'],
        'flash_attention': OLLAMA_ENV['OLLAMA_FLASH_ATTENTION'], 'kv_cache_type': OLLAMA_ENV['OLLAMA_KV_CACHE_TYPE']}
    identity_path = RESULT_DIR / 'run-identity.json'
    if identity_path.exists():
        assert json.loads(identity_path.read_text()) == identity, 'Phiên hiện tại khác manifest đã lưu. Dừng; không trộn nhãn.'
    else:
        assert not SFT.exists() and not LOG.exists(), 'Có SFT/log nhưng thiếu run-identity: dừng để kiểm tra.'
        identity_path.write_text(json.dumps(identity, ensure_ascii=False, indent=2), encoding='utf-8')

    def read_jsonl(path):
        return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()] if path.exists() else []

    def check_progress():
        logs, chats = read_jsonl(LOG), read_jsonl(SFT)
        assert len({r['id'] for r in logs}) == len(logs), 'Log trùng ID.'
        assert all(r['id'] in by_id and r.get('filter_version') == FILTER_VERSION for r in logs), 'Log sai bộ dữ liệu/phiên bản.'
        expected = {r['id'] + '-' + str(i) for r in logs if r['kept'] for i in (0, 1)}
        ids = [r['id'] for r in chats]
        assert len(ids) == len(set(ids)) and set(ids) == expected, 'SFT/log chưa khớp (có thể bị ngắt giữa lúc ghi). Dừng, giữ nguyên file để kiểm tra.'
        return logs, chats

    logs, chats = check_progress()
    print('Đã xử lý:', len(logs), '/100 | Đã giữ:', sum(r['kept'] for r in logs), '| Bản ghi SFT:', len(chats))
    environment = {'at': datetime.now(timezone.utc).isoformat(), 'identity': identity,
        'gpu': gpu_info, 'loaded_model': loaded,
        'packages': json.loads(subprocess.check_output([PYTHON, '-m', 'pip', 'list', '--format=json'], text=True))}
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    (RESULT_DIR / ('environment-' + stamp + '.json')).write_text(json.dumps(environment, ensure_ascii=False, indent=2), encoding='utf-8')

    def run_teacher(limit):
        check_progress()
        if limit <= 0:
            print('Không có câu mới cần chạy ở bước này.')
            return
        command = [PYTHON, '-u', '-m', 'training.teacher', '--model', MODEL,
            '--requests', str(REQUESTS), '--output', str(SFT), '--ollama-url', OLLAMA_URL,
            '--num-ctx', str(NUM_CTX), '--timeout', '600', '--limit', str(limit)]
        console_path = RESULT_DIR / 'teacher-console.log'
        with console_path.open('a', encoding='utf-8') as console:
            process = subprocess.Popen(command, cwd=WORK, stdout=console, stderr=subprocess.STDOUT)
            last_count = -1
            try:
                while process.poll() is None:
                    lines = LOG.read_text(encoding='utf-8').splitlines(keepends=True) if LOG.exists() else []
                    completed_lines = [line for line in lines if line.endswith('\\n') and line.strip()]
                    if len(completed_lines) != last_count:
                        print(f'Đã ghi log {len(completed_lines)}/100 yêu cầu', flush=True)
                        last_count = len(completed_lines)
                    time.sleep(5)
                assert process.returncode == 0, f'Teacher dừng lỗi. Xem {console_path}'
            except BaseException:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                raise
        print(console_path.read_text(encoding='utf-8')[-5000:])
        logs, chats = check_progress()
        print('Đã xử lý:', len(logs), '| Giữ:', sum(r['kept'] for r in logs), '| Bỏ:', sum(not r['kept'] for r in logs))
        print('Lý do loại:', dict(Counter(r['reason'] for r in logs if not r['kept'])))
    ''')
    md('''
    ## 8. Chạy thử tối đa 5 yêu cầu đầu tiên

    Đổi `RUN_FIRST_5 = True` rồi chạy ô này. Chỉ thử teacher, không train.
    Gửi kết quả/log để xem chất lượng trước khi mở phần còn lại. Chạy lại ô không tự thêm 5 câu mới nếu đã đủ 5.
    ''')
    code('''
    RUN_FIRST_5 = False
    if RUN_FIRST_5:
        logs, _ = check_progress()
        run_teacher(max(0, 5 - len(logs)))
    else:
        print('Chưa gọi teacher. Đổi RUN_FIRST_5=True khi muốn chạy thử 5 câu.')
    ''')
    md('''
    ## 9. Xem nhãn đã giữ để đọc tay

    Nhãn hiển thị ở đây là nhãn teacher thô đã qua bộ lọc; vẫn cần đọc và đối chiếu câu lệnh/context.
    Không coi mọi nhãn hợp lệ là hoàn hảo. Các câu bị loại không có nhãn trong SFT; lý do nằm ở log.
    ''')
    code('''
    logs, chats = check_progress()
    kept_ids = [r['id'] for r in logs if r['kept']]
    for request_id in kept_ids[:5]:
        source = by_id[request_id]
        print('\\nID:', request_id, '| Nhóm:', source['kind'])
        print('Câu lệnh:', source['request']['instruction'])
        for chat in chats:
            if chat['id'].rsplit('-', 1)[0] == request_id:
                print(chat['id'], chat['messages'][-1]['content'])
    print('Chỉ xem tối đa 5 yêu cầu đầu tiên ở ô này; toàn bộ nhãn có trong SFT trên Drive.')
    ''')
    md('''
    ## 10. Chạy tiếp đến đủ 100 yêu cầu đã xử lý

    Chỉ đổi `CONTINUE_AFTER_REVIEW = True` sau khi đã kiểm tra 5 câu đầu. Nếu nhóm quan trọng sai hoặc bị loại hết, dừng và điều tra; không hạ chuẩn để đủ quota.
    Hoàn tất 100 đầu vào không đồng nghĩa có 100 yêu cầu đạt sau lọc.
    ''')
    code('''
    CONTINUE_AFTER_REVIEW = False
    if CONTINUE_AFTER_REVIEW:
        logs, _ = check_progress()
        assert len(logs) >= 5, 'Chạy thử và xem kết quả 5 câu đầu trước.'
        run_teacher(max(0, 100 - len(logs)))
    else:
        print('Chưa chạy phần còn lại. Giữ nguyên False để dừng sau bước xem kết quả.')
    ''')
    md("## 11. Báo cáo pilot và danh sách nhãn cần đọc — không chia tập hoặc train")
    code('''
    logs, chats = check_progress()
    stats = {}
    for kind in sorted({row['kind'] for row in requests}):
        selected = [entry for entry in logs if by_id[entry['id']]['kind'] == kind]
        stats[kind] = {'requested': sum(row['kind'] == kind for row in requests),
            'processed': len(selected), 'kept': sum(entry['kept'] for entry in selected),
            'dropped': sum(not entry['kept'] for entry in selected)}
    summary = {'status': 'processed_100_needs_manual_review' if len(logs) == 100 else 'partial',
        'identity': identity, 'processed': len(logs), 'total_inputs': 100,
        'kept': sum(row['kept'] for row in logs), 'sft_records': len(chats),
        'drop_reasons': dict(Counter(row['reason'] for row in logs if not row['kept'])),
        'by_kind': stats, 'manual_review': 'pending', 'tokenizer_audit': 'pending', 'training_started': False}
    (RESULT_DIR / 'pilot-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    review = []
    for entry in logs:
        if entry['kept']:
            review.append({'id': entry['id'], 'kind': by_id[entry['id']]['kind'],
                'request': by_id[entry['id']]['request'], 'expect': by_id[entry['id']]['expect'],
                'chats': [chat for chat in chats if chat['id'].rsplit('-', 1)[0] == entry['id']],
                'manual_review': 'pending'})
    (RESULT_DIR / 'pilot-label-review.jsonl').write_text(''.join(json.dumps(row, ensure_ascii=False) + '\\n' for row in review), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print('Gửi pilot-summary.json và log để kiểm tra. Chưa hợp nhất dữ liệu, chưa train.')
    ''')
    md('''
    ## Sau khi chạy xong

    Kết quả: `taskmanly-train/v2-20261104/pilot/teacher-output/` trên Drive.
    Giữ `sft.jsonl`, `sft.log.jsonl`, `run-identity.json`, `pilot-summary.json` và `pilot-label-review.jsonl`.
    Nếu phiên ngắt, chạy lại ô 1–7 trong notebook này; chỉ những ID chưa có log sẽ được teacher xử lý tiếp.
    Không sửa log để chạy lại câu bị loại. Thí nghiệm khác dùng output/run riêng và có ghi nhận thay đổi.

    Trước train: đọc tay nhãn pilot, kiểm toán đầu ra và nhóm bị loại, sau đó mới quyết định mở rộng dữ liệu.
    Có thể ngắt runtime Colab sau khi kiểm tra kết quả đã lưu trên Drive.

    Tham khảo thiết lập: [Ollama Linux](https://docs.ollama.com/linux), [API chat](https://docs.ollama.com/api/chat), [GPU/model đang chạy](https://docs.ollama.com/api/ps).
    ''')
    for index, cell in enumerate(cells):
        cell['id'] = f'pilot-v2-{index:02d}'
    return {'nbformat': 4, 'nbformat_minor': 5,
        'metadata': {'colab': {'name': 'taskmanly-pilot-v2.ipynb', 'provenance': [], 'gpuType': 'T4'},
            'accelerator': 'GPU', 'kernelspec': {'name': 'python3', 'display_name': 'Python 3'},
            'language_info': {'name': 'python'}}, 'cells': cells}


if __name__ == '__main__':
    OUTPUT.write_text(json.dumps(build(), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(OUTPUT)
