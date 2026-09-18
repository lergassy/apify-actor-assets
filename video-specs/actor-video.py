#!/usr/bin/env python3
"""Монтаж демо-ролика актора: экран с преимуществами, затем запись, поверх — субтитры.

Ролик снимает Матвей, здесь он только собирается. Порядок задан им: сначала первый экран
с конкурентными преимуществами, потом демонстрация, субтитры подсвечивают важное.

Текст рисуется через Pillow и накладывается как PNG: ffmpeg на этой машине собран без
freetype и libass, поэтому ни drawtext, ни subtitles не работают — overlay работает всегда.

  python3 scripts/actor-video.py <исходник.mov> <spec.json> <выход.mp4>
"""
import json, subprocess, sys, tempfile, os
from PIL import Image, ImageDraw, ImageFont

BOLD = '/System/Library/Fonts/Supplemental/Arial Bold.ttf'
REG = '/System/Library/Fonts/Supplemental/Arial.ttf'
INK = (14, 27, 61)          # тёмный фон в цвет иконки актора
ACCENT = (45, 136, 255)
WHITE = (255, 255, 255)
MUTED = (168, 190, 224)

font = lambda p, s: ImageFont.truetype(p, s)


def intro_png(spec, w, h, path):
    """Первый экран: название, обещание, преимущества."""
    im = Image.new('RGB', (w, h), INK)
    d = ImageDraw.Draw(im)
    k = w / 1920                                     # всё в масштабе от 1920 по ширине
    x = int(150 * k)
    y = int(230 * k)
    d.text((x, y), spec['title'], font=font(BOLD, int(78 * k)), fill=WHITE)
    y += int(120 * k)
    d.text((x, y), spec['subtitle'], font=font(REG, int(40 * k)), fill=MUTED)
    y += int(110 * k)
    for line in spec['bullets']:
        d.rounded_rectangle([x, y + int(14 * k), x + int(14 * k), y + int(44 * k)],
                            radius=int(7 * k), fill=ACCENT)
        d.text((x + int(42 * k), y), line, font=font(BOLD, int(46 * k)), fill=WHITE)
        y += int(88 * k)
    if spec.get('footer'):
        d.text((x, h - int(150 * k)), spec['footer'], font=font(REG, int(36 * k)), fill=ACCENT)
    im.save(path)


def caption_png(text, note, w, path):
    """Плашка субтитра с прозрачным фоном: сама плашка непрозрачная, поля вокруг — нет."""
    k = w / 1920
    pad = int(34 * k)
    f1, f2 = font(BOLD, int(46 * k)), font(REG, int(34 * k))
    probe = ImageDraw.Draw(Image.new('RGBA', (10, 10)))
    tw = probe.textlength(text, font=f1)
    nw = probe.textlength(note, font=f2) if note else 0
    bw = int(max(tw, nw) + pad * 2)
    bh = int((110 if note else 64) * k + pad)
    im = Image.new('RGBA', (bw, bh), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, bw - 1, bh - 1], radius=int(18 * k), fill=INK + (235,))
    d.rounded_rectangle([0, 0, int(8 * k), bh - 1], radius=int(4 * k), fill=ACCENT + (255,))
    d.text((pad, int(pad * 0.55)), text, font=f1, fill=WHITE)
    if note:
        d.text((pad, int(pad * 0.55 + 56 * k)), note, font=f2, fill=MUTED)
    im.save(path)


def main():
    src, spec_path, out = sys.argv[1], sys.argv[2], sys.argv[3]
    spec = json.load(open(spec_path))
    probe = json.loads(subprocess.run(
        ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
         'stream=width,height', '-of', 'json', src], capture_output=True, text=True).stdout)
    sw, sh = probe['streams'][0]['width'], probe['streams'][0]['height']
    # Нечётные стороны h264 не принимает, а запись экрана Mac их даёт регулярно.
    ow, oh = spec.get('width', 1920), spec.get('height', int(1920 * sh / sw) // 2 * 2)

    tmp = tempfile.mkdtemp(prefix='actor-video-')
    intro = os.path.join(tmp, 'intro.png')
    intro_png(spec['intro'], ow, oh, intro)

    inputs = ['-loop', '1', '-t', str(spec.get('introSeconds', 5)), '-i', intro, '-i', src]
    overlays, filters = [], []
    for i, c in enumerate(spec['captions']):
        p = os.path.join(tmp, f'cap{i}.png')
        caption_png(c['text'], c.get('note', ''), ow, p)
        inputs += ['-i', p]
        overlays.append((i + 2, c['from'], c['to']))

    # Масштабируем запись, накладываем субтитры, приклеиваем интро впереди.
    filters.append(f'[1:v]scale={ow}:{oh}:flags=lanczos,setsar=1,fps=30[body]')
    prev = 'body'
    y = spec.get('captionY', 0.80)
    for n, (idx, t0, t1) in enumerate(overlays):
        tag = f'ov{n}'
        filters.append(
            f"[{prev}][{idx}:v]overlay=x={int(ow*0.045)}:y=H*{y}-h:"
            f"enable='between(t,{t0},{t1})'[{tag}]")
        prev = tag
    filters.append(f'[0:v]scale={ow}:{oh},setsar=1,fps=30[intro]')
    filters.append(f'[intro][{prev}]concat=n=2:v=1:a=0[out]')

    cmd = ['ffmpeg', '-y', *inputs, '-filter_complex', ';'.join(filters),
           '-map', '[out]', '-c:v', 'libx264', '-preset', 'slow', '-crf', '20',
           '-pix_fmt', 'yuv420p', '-movflags', '+faststart', out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        print(r.stderr[-2500:]); sys.exit(1)
    print('готово:', out)


if __name__ == '__main__':
    main()
