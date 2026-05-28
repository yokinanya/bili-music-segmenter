import asyncio
import glob
import logging
import os
import tempfile

from segment.segment import (
    SEGMENT_THRES,
    TimestampMismatch,
    extract_mah_stuff,
    extract_music,
    segment_wrapper,
)
from segment.netease import netease_coverart, netease_orig, neteasing
from segment.shazam import (
    recognize_files,
    shazam_coverart,
    shazam_orig,
    shazaming,
)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='ina music segment')
    parser.add_argument('--media', type=str, help='local media file path')
    parser.add_argument(
        '--outdir', type=str, default=tempfile.gettempdir(),
        help='directory extracted files will be written into')
    parser.add_argument(
        '--shazam', action='store_true', default=False,
        help='shazam the extracted files')
    parser.add_argument(
        '--shazam_coverart', type=str, default='',
        help='save shazam cover art too')
    parser.add_argument(
        '--netease', action='store_true', default=False,
        help='recognize extracted files with a NetEase recognizer service')
    parser.add_argument(
        '--netease_endpoint', type=str, default='',
        help='NetEase recognizer service endpoint accepting multipart file')
    parser.add_argument(
        '--netease_coverart', type=str, default='',
        help='save NetEase cover art when returned by the service')
    parser.add_argument(
        '--netease_cookie', type=str, default='',
        help='NetEase cookie passed through to NeteaseCloudMusicApi')
    parser.add_argument(
        '--netease_timeout', type=int, default=60,
        help='NetEase recognizer request timeout in seconds')
    parser.add_argument(
        '--netease_offsets', type=str, default='6,12,20,30',
        help='comma-separated seconds to try before generating NetEase audioFP')
    parser.add_argument(
        '--netease_rejects', type=str, default='劫|黄霄雲',
        help='comma-separated NetEase matches to reject, formatted title|artist')
    parser.add_argument(
        '--recognizer_fallback', action='store_true', default=False,
        help='fallback to the other recognizer when the selected one fails')
    parser.add_argument(
        '--soundonly', action='store_true', default=True,
        help='extract audio-only MP3 segments')
    parser.add_argument(
        '--keep_video', action='store_false', dest='soundonly',
        help='extract video/audio segments without converting to MP3')
    parser.add_argument(
        '--seg_connect', type=int, default=5,
        help='max seconds for 2 music segments to be considered \
            the same (takes care of random miss-detection/small rap segments)')
    parser.add_argument(
        '--cleanup', action='store_true', default=False,
        help='delete the original media file once completed.')
    parser.add_argument(
        '--max_segment_length',
        type=int,
        default=SEGMENT_THRES,
        help='for computers with limited RAM (eg a 5 hrs stream \
            requires ~6GB VRAM), set this to process streams in \
                this speficied segments to avoid ram overflow. in seconds.')
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s %(levelname)-8s %(message)s',
        handlers=[
            logging.FileHandler('./inaseg_inst.log'),
            logging.StreamHandler()
        ])
    args = parser.parse_args()
    if args.media is not None:
        media = args.media
    else:
        raise Exception('no media')
    if not os.path.isfile(media):
        raise FileNotFoundError(media)
    if args.shazam and args.netease:
        raise ValueError('choose only one recognizer: --shazam or --netease')
    if args.recognizer_fallback and not (args.shazam or args.netease):
        raise ValueError('--recognizer_fallback requires --shazam or --netease')
    if (args.netease or args.recognizer_fallback) and not args.netease_endpoint:
        raise ValueError('--netease_endpoint is required with --netease')
    os.makedirs(args.outdir, exist_ok=True)
    if len(glob.glob(os.path.join(
            args.outdir,
            f'*{os.path.splitext(os.path.basename(media))[0][1:]}_*'))) == 0:
        import tensorflow as tf
        gpus = tf.config.experimental.list_physical_devices('GPU')
        logging.info(gpus)
        tf.get_logger().setLevel(logging.WARNING)
        try:
            timestamps = []
            saved_timestamp = extract_music(segment_wrapper(
                media, segment_length_thres=args.max_segment_length),
                segment_connect=args.seg_connect)
            extract_mah_stuff(
                media, segmented_stamps=saved_timestamp,
                outdir=args.outdir, rev=False,
                timestamps=timestamps,
                soundonly=args.soundonly)
            saved_timestamp = None
        except TimestampMismatch:
            raise
    else:
        logging.warning((
            'segmentation', media, 'stopped to prevent posssible duplication'))
    logging.info(['segmentation', media, 'successful'])
    if args.cleanup and os.path.isfile(media):
        os.remove(media)
    if args.shazam and args.recognizer_fallback:
        async def myfallback():
            async def recognizer(file):
                try:
                    return await shazam_orig(file)
                except Exception as error:
                    logging.warning([
                        'shazam failed, falling back to netease',
                        os.path.basename(file),
                        repr(error),
                    ])
                    return await netease_orig(
                        file,
                        endpoint=args.netease_endpoint,
                        cookie=args.netease_cookie,
                        offsets=args.netease_offsets,
                        rejects=args.netease_rejects,
                        timeout=args.netease_timeout,
                    )
            await recognize_files(
                args.outdir,
                media,
                recognizer_func=recognizer,
                provider_name='shazam_netease',
                coverart_path=args.shazam_coverart,
                coverart_func=shazam_coverart,
            )
        loop = asyncio.get_event_loop()
        loop.run_until_complete(myfallback())
        loop.close()
    elif args.shazam:
        async def myshazam():
            await shazaming(
                args.outdir, media, args.shazam_coverart,)
        loop = asyncio.get_event_loop()
        loop.run_until_complete(myshazam())
        loop.close()
    if args.netease and args.recognizer_fallback:
        async def myfallback():
            async def recognizer(file):
                try:
                    return await netease_orig(
                        file,
                        endpoint=args.netease_endpoint,
                        cookie=args.netease_cookie,
                        offsets=args.netease_offsets,
                        rejects=args.netease_rejects,
                        timeout=args.netease_timeout,
                    )
                except Exception as error:
                    logging.warning([
                        'netease failed, falling back to shazam',
                        os.path.basename(file),
                        repr(error),
                    ])
                    return await shazam_orig(file)
            await recognize_files(
                args.outdir,
                media,
                recognizer_func=recognizer,
                provider_name='netease_shazam',
                coverart_path=args.netease_coverart,
                coverart_func=netease_coverart,
            )
        loop = asyncio.get_event_loop()
        loop.run_until_complete(myfallback())
        loop.close()
    elif args.netease:
        async def mynetease():
            await neteasing(
                args.outdir,
                media,
                endpoint=args.netease_endpoint,
                cookie=args.netease_cookie,
                offsets=args.netease_offsets,
                rejects=args.netease_rejects,
                coverart_path=args.netease_coverart,
                timeout=args.netease_timeout,
            )
        loop = asyncio.get_event_loop()
        loop.run_until_complete(mynetease())
        loop.close()
    import sys
    sys.exit(0)
