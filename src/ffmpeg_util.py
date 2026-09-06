import shutil
import warnings

warnings.filterwarnings(
    "ignore",
    message="Couldn't find ffmpeg|Couldn't find ffplay|Couldn't find avconv",
    module="pydub.*",
)


def get_ffmpeg_exe():
    """Return a usable ffmpeg executable, preferring the imageio-ffmpeg static binary."""
    from_path = shutil.which("ffmpeg")
    if from_path:
        return from_path
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def get_ffprobe_exe():
    """Return a usable ffprobe executable, preferring the imageio-ffmpeg static binary."""
    from_path = shutil.which("ffprobe")
    if from_path:
        return from_path
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffprobe"


def configure_pydub():
    """Point pydub's converter/ffprobe at the resolved ffmpeg binaries."""
    from pydub import AudioSegment
    ffmpeg = get_ffmpeg_exe()
    AudioSegment.converter = ffmpeg
    AudioSegment.ffprobe = get_ffprobe_exe()