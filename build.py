# -*- coding: utf-8 -*-
"""
LoonScripts 数据构建脚本
用法:
    python build.py

做什么:
    1. 增量更新本地 partial clone 缓存 (cache/romeo)
    2. 用 git log 计算 Modules/Loon 下每个文件的最后提交时间(即脚本最新更新时间)
    3. 解析每个 .lpx/.plugin 文件头部的元数据 (#!name/#!desc/#!author/#!date) 与质量
    4. 结合 name_map.json 做中文名映射 -> 生成 data.js (index.html 直接读取)

输出: data.js (+ cache/unresolved.txt 未映射清单)
"""
import json
import os
import re
import subprocess
import concurrent.futures
import urllib.parse
import urllib.request
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(ROOT, 'cache')
REPO = os.path.join(CACHE, 'romeo')
REPO_URL = 'https://github.com/ifflagged/Romeo.git'
BRANCH = 'main'
RAW_BASE = 'https://raw.githubusercontent.com/ifflagged/Romeo/%s/' % BRANCH
PREFIX = 'Modules/Loon/'

CJK = re.compile(r'[\u4e00-\u9fff]')


def log(*a):
    print(*a, flush=True)


# ---------------------------------------------------------------- git ----
def git(*args, check=False):
    cmd = ['git', '-c', 'core.protectNTFS=false', '-c', 'core.quotepath=false'] + list(args)
    cwd = REPO if os.path.isdir(os.path.join(REPO, '.git')) else ROOT
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    if check and p.returncode != 0:
        raise RuntimeError('git %s failed:\n%s' % (' '.join(args), p.stderr))
    return p


def ensure_repo():
    if not os.path.isdir(os.path.join(REPO, '.git')):
        log('首次运行: 克隆仓库 (partial clone, 约 15MB)...')
        subprocess.run(['git', 'clone', '--filter=blob:none', '--no-checkout',
                        '--single-branch', '--branch', BRANCH, REPO_URL, REPO],
                       check=True)
    log('更新仓库缓存 (git fetch)...')
    git('fetch', '--quiet', 'origin', BRANCH)
    git('sparse-checkout', 'set', '--no-cone', '/Modules/Loon/**', '/Links/**')
    p = git('reset', '--hard', 'origin/' + BRANCH)
    if p.returncode != 0:
        log('  reset 警告(通常无关紧要):', (p.stderr or '').strip()[:200])


def head_sha():
    p = git('rev-parse', 'origin/' + BRANCH)
    return (p.stdout or '').strip()


def file_dates():
    """path -> 最后提交时间 (ISO), 只统计实际内容提交(--no-merges)"""
    log('计算每个文件的最后提交时间 ...')
    p = git('log', '--format=DT%cI', '--name-only', '--no-merges', '--', PREFIX)
    dates, cur = {}, None
    for line in (p.stdout or '').splitlines():
        line = line.strip()
        if line.startswith('DT'):
            cur = line[2:]
        elif line.startswith(PREFIX) and line not in dates:
            dates[line] = cur
    log('  共 %d 个文件有提交时间' % len(dates))
    return dates


def tree_files():
    """从 git 取权威文件清单: path -> size"""
    p = git('ls-tree', '-r', '-l', 'origin/' + BRANCH, '--', PREFIX)
    out = {}
    for line in (p.stdout or '').splitlines():
        try:
            meta, path = line.split('\t', 1)
            parts = meta.split()
            if len(parts) >= 4 and parts[1] == 'blob':
                out[path] = int(parts[3])
        except Exception:
            continue
    return out


# ------------------------------------------------------------- parsing ----
HDR_RE = re.compile(r'^#!\s*([A-Za-z_][\w\-]*)\s*=\s*(.*)$')


def parse_header_text(text):
    meta = {}
    for line in text.splitlines()[:150]:
        line = line.strip().lstrip('\ufeff')
        if not line.startswith('#!'):
            if meta or line.startswith('['):
                break
            continue
        m = HDR_RE.match(line)
        if m:
            meta.setdefault(m.group(1).lower(), m.group(2).strip())
    return meta


def quality_of(text):
    """'' | 'bad'(同步失败产物) | 'empty'(空壳)"""
    if 'Error: Response code' in text[:5000] or 'Error: Not Found' in text[:5000] or \
       text[:200].lstrip().lower().startswith('<!doctype'):
        return 'bad'
    body = re.sub(r'^#!.*$', '', text, flags=re.M)
    if not re.search(r'^\s*\[', text, re.M) and len(body.strip()) < 200:
        return 'empty'
    return ''


def parse_local(path):
    try:
        with open(os.path.join(REPO, path), 'rb') as f:
            text = f.read(262144).decode('utf-8', errors='replace')
        return parse_header_text(text), quality_of(text)
    except OSError:
        return None, ''


def parse_remote(path):
    url = RAW_BASE + urllib.parse.quote(path)
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'LoonScripts-build'})
            with urllib.request.urlopen(req, timeout=20) as r:
                text = r.read(262144).decode('utf-8', errors='replace')
            return parse_header_text(text), quality_of(text)
        except Exception:
            import time
            time.sleep(1 + attempt)
    return {}, ''


# ---------------------------------------------------------- name tools ----
STRIP_SUFFIXES = [
    '_remove_ads', '-remove_ads', '.remove_ads', '_remove_ad', 'remove_ads', '_removeads',
    '_no_ads', '_noads', '_no_ad', '_ads', '.ads', 'noads', 'noad', 'ads',
    '_blockads', 'blockads', '_adblock', 'adblock', '_unblock', '_clean', '_lite', '_pro',
    '_custom', '-custom', '_enhance', '_enhanced', '_helper', '_checkin',
    '_mount', '_data', '_beta', '_official', '_vip', '_crack', '_unlock',
]
DOT_KEYWORDS = {'ads', 'ad', 'adblock', 'adblocker', 'adblocklite', 'vip', 'no', 'lite', 'pro',
                'beta', 'official', 'custom', 'enhance', 'enhanced', 'helper', 'checkin',
                'mount', 'remove', 'remover', 'block', 'blocker', 'clean', 'cleaner',
                'purify', 'unlock', 'unblock', 'json', 'fnc', 'get', 'min', 'ads2', 'ad2',
                'fix', 'response', 'request', 'beta2', 'dev'}

QUAL_MAP = {
    'enhance': '增强', 'enhanced': '增强', 'experimental': '实验版',
    'adblock': '去广告', 'adblocker': '去广告', 'ads': '去广告',
    'noad': '去广告', 'noads': '去广告', 'removeads': '去广告',
    'unlock': '解锁', 'vip': '解锁', 'crack': '解锁',
    'helper': '助手', 'checkin': '签到', 'signin': '签到', 'sign': '签到',
    'monitor': '监控', 'redirect': '重定向', 'lite': '精简版',
    'clean': '清理', 'cleaner': '清理', 'repair': '修复', 'fix': '修复',
    'price': '比价', 'extra': '扩展', 'plus': '增强', 'general': '通用',
    'common': '通用', 'tools': '工具', 'tool': '工具', 'pure': '纯净版',
    'auto': '自动', 'applet': '小程序', 'app': '', 'beta': 'Beta',
    'block': '拦截', 'purify': '净化',
}
HEADER_SUFFIX = {'rewrite': '重写', 'beta': 'Beta', 'dev': '测试', 'lite': '精简', 'pro': 'Pro'}


def norm(s):
    return re.sub(r'[^a-z0-9]+', '', s.lower())


def stem_of(fname):
    base = fname
    for ext in ('.lpx', '.plugin'):
        if base.lower().endswith(ext):
            base = base[:-len(ext)]
    return re.sub(r'\.bundle$', '', base, flags=re.I)


def token_keys(fname):
    """候选查询键: [去掉通用后缀的, 原名, 点分段, 首段]"""
    base = stem_of(fname)
    keys = []

    def add(k):
        k = norm(k)
        if len(k) >= 3 and k not in keys:
            keys.append(k)

    s = base
    changed = True
    while changed:
        changed = False
        low = s.lower()
        for suf in STRIP_SUFFIXES:
            if low.endswith(suf) and len(s) > len(suf) + 1:
                s = s[:len(s) - len(suf)]
                changed = True
                break
    add(s)
    add(base)
    if '.' in base:
        segs = [seg for seg in base.split('.') if seg]
        keep = [seg for seg in segs if norm(seg) not in DOT_KEYWORDS]
        if keep:
            add(keep[0])
            add(''.join(keep))
    if '_' in base or '-' in base:
        first = re.split(r'[_\-]', base)[0]
        add(first)
    return keys


EMOJI_RE = re.compile(
    '[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\u2190-\u21FF\uFE0F\u200D'
    '\uE000-\uF8FF\uFDFD\u2764\u2049]')


def clean_text(s):
    s = s.replace('\\n', ' ').replace('\r', ' ').replace('\n', ' ')
    s = EMOJI_RE.sub(' ', s)
    s = re.sub(r'\s+', ' ', s)
    s = re.sub(r'@[A-Za-z0-9_\-]+$', '', s)
    return s.strip(' :：-·|')


APP_STRIP = ['去广告', '移除广告', '广告净化', '广告拦截', '拦截广告', '净化', '增强', '解锁',
             '精简', '去推广', '移除推广', '去开屏', '优化', '补丁', '（测试版）', '(测试版)']


def app_from_zh(nm):
    s = clean_text(nm)
    s = re.sub(r'\s*[-–—]\s*[A-Za-z0-9 ,._|+]+$', '', s)
    s = s.split('：')[0].split(':')[0].strip()
    s = clean_text(s)
    for _ in range(3):
        stripped = False
        for suf in APP_STRIP:
            if s.endswith(suf) and len(s) > len(suf) + 1:
                s = s[:-len(suf)].strip()
                stripped = True
        if not stripped:
            break
    if s.endswith('版') and len(s) > 3:
        s = s[:-1]
    s = re.sub(r'[（(][^）)]*[）)]$', '', s).strip()
    if len(s) > 16 or not (2 <= len(s)):
        return ''
    if any(w in s for w in ['合集', '模块', '查询', '网页', '管理', '工具', '重定向']) and len(s) > 10:
        return ''
    return s


def qualifiers_from(stem):
    segs = re.split(r'[.\-_ ]+', stem.lower())
    found = []
    for s in segs:
        if not s:
            continue
        if s in QUAL_MAP:
            v = QUAL_MAP[s]
            if v and v not in found:
                found.append(v)
            continue
        for q in sorted((k for k in QUAL_MAP if len(k) >= 3), key=len, reverse=True):
            if s.endswith(q) and len(s) > len(q):
                v = QUAL_MAP[q]
                if v and v not in found:
                    found.append(v)
                break
        if len(found) >= 2:
            break
    return found


def join_name(base, qual):
    if not qual:
        return base
    sep = '' if (CJK.search(base[-1]) and CJK.search(qual[0])) else ' '
    return base + sep + qual


# ---------------------------------------------------------------- main ----
def main():
    ensure_repo()
    sha = head_sha()
    dates = file_dates()
    files = tree_files()
    log('仓库当前共 %d 个 Loon 模块文件' % len(files))

    metas, qflags, remote_todo = {}, {}, []
    for path in files:
        m, q = parse_local(path)
        if m is None:
            remote_todo.append(path)
        else:
            metas[path] = m
            qflags[path] = q
    if remote_todo:
        log('本地缺失 %d 个文件, 走 raw 链接解析...' % len(remote_todo))
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            futs = {ex.submit(parse_remote, p): p for p in remote_todo}
            for fut in concurrent.futures.as_completed(futs):
                p = futs[fut]
                m, q = fut.result()
                metas[p] = m or {}
                qflags[p] = q

    name_map = json.load(open(os.path.join(ROOT, 'name_map.json'), encoding='utf-8'))
    aliases = name_map.get('_aliases', {})
    name_map = {k: v for k, v in name_map.items() if not k.startswith('_')}

    # 中文对照库: key -> Counter(app中文名)
    zh_counter = defaultdict(Counter)
    for path, m in metas.items():
        nm = m.get('name', '')
        if not nm or not CJK.search(nm):
            continue
        app = app_from_zh(nm)
        if not app:
            continue
        for k in token_keys(path.split('/')[-1]):
            zh_counter[k][app] += 1

    def resolve_app(fname, plugin_nm):
        nb = norm(stem_of(fname))
        if nb in name_map:                  # 0. 短名直查(gwps/jd/t3/qx 等)
            return name_map[nb]
        keys = token_keys(fname)
        for k in keys:                      # 1. 人工字典
            if k in name_map:
                return name_map[k]
        cands = Counter()                   # 2. 跨作者中文对照
        for k in keys:
            if k in zh_counter:
                cands.update(zh_counter[k])
        if cands:
            return cands.most_common(1)[0][0]
        if CJK.search(plugin_nm or ''):     # 3. 插件名里的中文
            a = app_from_zh(plugin_nm)
            if a:
                return a
        return ''

    def special_title(stem):
        """DualSubs.X / iRingo.X 组合命名"""
        low = stem.lower()
        for pref, disp in (('dualsubs.', 'DualSubs'), ('iringo.', 'iRingo'),
                           ('iringo_', 'iRingo')):
            if not low.startswith(pref):
                continue
            tails = [t for t in re.split(r'[._]', stem)[1:]
                     if t.lower() not in ('addon', 'rewrite')]
            parts = []
            for t in tails:
                parts.append(name_map.get(norm(t), clean_text(t)))
            sub = ''.join(parts)
            if disp == 'DualSubs':
                return '%s · %s' % (disp, sub or '字幕'), 'DualSubs'
            return '%s · %s' % (disp, sub), 'iRingo'
        return None, None

    entries = []
    unresolved = Counter()
    for path, size in sorted(files.items()):
        m = metas.get(path, {})
        fname = path.split('/')[-1]
        parts = path[len(PREFIX):].split('/')
        author = re.sub(r'\.(lpx|plugin)$', '', parts[0], flags=re.I)  # 根目录合并插件: Jacob.lpx -> Jacob
        channel = parts[1] if len(parts) >= 3 else ''
        stem = stem_of(fname)
        plugin_nm = clean_text(m.get('name', '')) or stem
        dep = 1 if '.bundle' in fname else 0

        st, sgroup = special_title(stem)
        if st:
            title, app = st, sgroup
        else:
            app = resolve_app(fname, m.get('name', ''))
            if CJK.search(plugin_nm):
                title = plugin_nm
            else:
                quals = qualifiers_from(stem)
                if app:
                    title = join_name(app, quals[0] if quals else '')
                else:
                    title = join_name(stem, quals[0] if quals else '')
                    unresolved[stem] += 1
        if not app:
            app = title

        desc = clean_text(m.get('desc', ''))[:120]
        entries.append({
            'p': path, 'a': author, 'c': channel, 'g': app, 'n': title,
            'd': desc, 't': dates.get(path, ''), 'dm': clean_text(m.get('date', ''))[:19],
            'tag': clean_text(m.get('tag', ''))[:16], 'sz': size, 'dep': dep,
            'q': qflags.get(path, ''), 'v': clean_text(m.get('version', ''))[:12],
            'al': aliases.get(norm(stem), ''),
        })

    import datetime
    data = {
        'generated': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'repo': 'https://github.com/ifflagged/Romeo',
        'commit': sha[:10],
        'count': len(entries),
        'entries': entries,
    }
    out_js = os.path.join(ROOT, 'data.js')
    js = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    with open(out_js, 'w', encoding='utf-8') as f:
        f.write('window.LOON_DATA=' + js + ';\n')

    # 统计
    n_dep = sum(1 for e in entries if e['dep'])
    n_bad = sum(1 for e in entries if e['q'])
    n_dated = sum(1 for e in entries if e['t'])
    log('')
    log('=== 完成 ===')
    log('条目: %d (依赖组件 %d, 失效/空 %d, 有更新时间 %d)' % (len(entries), n_dep, n_bad, n_dated))
    log('data.js 大小: %.1f KB' % (os.path.getsize(out_js) / 1024))
    if unresolved:
        with open(os.path.join(CACHE, 'unresolved.txt'), 'w', encoding='utf-8') as f:
            for k, v in unresolved.most_common():
                f.write('%s\t%d\n' % (k, v))
        log('未映射英文名 %d 种 (见 cache/unresolved.txt), 前 20:' % len(unresolved))
        for k, v in unresolved.most_common(20):
            log('   %-30s x%d' % (k, v))


if __name__ == '__main__':
    main()
