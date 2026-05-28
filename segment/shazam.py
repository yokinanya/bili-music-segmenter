import glob
import logging
import os
import shutil
import time
import asyncio

import regex
import requests
from shazamio import Shazam

from utils.logging import save_timestamps


semaphore = asyncio.Semaphore(3)
myshazam = Shazam()


async def shazam_orig(file, **kwargs):
    match = await shazam(file)
    return shazam_title(match), match


async def recognize_files(
    outdir,
    media,
    *,
    recognizer_func,
    provider_name,
    coverart_path='',
    coverart_func=None,
    ignore_fails=False,
):
    mediab = os.path.basename(media)
    files = glob.glob(os.path.join(
        outdir, '*' + os.path.splitext(mediab)[0][1:] + '_*'
    ))
    await asyncio.gather(*[recognize_file(
        file,
        recognizer_func=recognizer_func,
        provider_name=provider_name,
        coverart_path=coverart_path,
        coverart_func=coverart_func,
        ignore_fails=ignore_fails,
    ) for file in files])
    save_timestamps(mediab=mediab,
                    key=provider_name, val=[
                        os.path.basename(x)
                        for x in glob.glob(
                            os.path.join(
                                outdir, f"*{mediab[1: mediab.rfind('.')]}*")
                        )
                    ])


async def shazaming(
    outdir, media, shazam_coverart_path='',
    shazam_func=shazam_orig, ignore_fails=False
):
    await recognize_files(
        outdir,
        media,
        recognizer_func=shazam_func,
        provider_name='shazam',
        coverart_path=shazam_coverart_path,
        coverart_func=shazam_coverart,
        ignore_fails=ignore_fails,
    )


async def recognize_file(
    file,
    *,
    recognizer_func,
    provider_name,
    coverart_path='',
    coverart_func=None,
    ignore_fails=True,
):
    results = {}
    if ' by ' in file:
        return
    filename = file[:file.rfind('.')]
    fileext = file[len(filename):]
    fn = os.path.basename(filename)
    logging.info([provider_name, 'recognizing', fn])
    try:
        results[fn], match = await recognizer_func(file)
        try:
            logging.info([fn, provider_name, 'found to be', results[fn]])
        except UnicodeEncodeError:
            logging.warning(
                [fn, provider_name, 'found but cant show unicode burr durr'])
        renamed_file = os.path.join(
            os.path.dirname(file),
            (fn + f"_{results[fn][0].replace(':', ' ')} by {results[fn][1].replace(r'/', '')}") + fileext
        )
        shutil.move(file, renamed_file)
        if os.path.isdir(coverart_path) and coverart_func is not None:
            coverart_func(match, renamed_file, coverart_path)
    except (IndexError, KeyError):
        logging.error([fn, provider_name, 'failed'])
        if not ignore_fails:
            raise
    except Exception:
        if not ignore_fails:
            raise


async def shazam(mp3):
    async with semaphore:
        match = await myshazam.recognize(mp3)
        time.sleep(3)
        return match['track']


def legalize_filename(fn):
    if regex.search(r'\p{IsHangul}', fn) is not None:
        raise KoreanCharException(fn)
    illegal_list = [
        [':', ' '],
        ['"', ''],
        [r'/', ''],
        [r'?', ''],
        [r'*', ''],
        ['\'', ''],
        ['<', ''],
        ['>', ''],
    ]
    for i in illegal_list:
        fn = fn.replace(i[0], i[1])
    return fn


def shazam_title(match):
    title = legalize_filename(match['title'])
    if 'in the style of' in title.lower():
        artist = title[
            title.lower().index('in the style of ') +
            len('in the style of '):]
        artist = artist[:artist.index(')')]
    else:
        artist = legalize_filename(match['subtitle'])

    return [
        legalize_filename(match['title']),
        legalize_filename(match['subtitle']),
    ]


def shazam_coverart(match, fn, outdir):
    try:
        albumart = match['images']['coverarthq']
        req = requests.get(albumart)
        with open(os.path.join(
            outdir, os.path.basename(fn) + albumart[albumart.rfind('.'):]
        ), 'wb') as f:
            f.write(req.content)
    except Exception:
        pass


class KoreanCharException(BaseException):
    pass
