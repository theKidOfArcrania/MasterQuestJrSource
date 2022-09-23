from bs4 import BeautifulSoup
from collections import OrderedDict, namedtuple
from subprocess import check_call, check_output
from PIL import Image, ImageFile
from hashlib import sha256
from functools import partial
import enum
import json
import shutil
import os
import os.path
import sys
import struct
import textwrap
import threading
import traceback
import zlib

SCRIPT_PATH = os.path.realpath(os.path.dirname(__file__))
IMAGEDATA_PATH = f'{SCRIPT_PATH}/imagedata'

# TODO: MAKE SURE StarRod is not running in background
try:
    import tkinter as tk
    from tkinter import messagebox, filedialog, dialog
    HEADLESS = False
except:
    HEADLESS = True

def error(msg):
    print(f'ERROR: {msg}')
    if not HEADLESS:
        messagebox.showerror(title="StarRodAux", message=msg)

def warn(msg, show=False):
    print(f'WARNING: {msg}')
    if not HEADLESS and show:
        messagebox.showwarning(title='StarRodAux', message=msg)

def info(msg, show=False):
    print(f'INFO: {msg}')
    if not HEADLESS and show:
        messagebox.showinfo(title='StarRodAux', message=msg)

def askyesno(msg):
    if HEADLESS:
        line = input(f'{msg} (y/N) ').upper()
        return line == 'Y' or line == 'YES'
    else:
        return messagebox.askyesno(title='StarRodAux', message=msg)


class Palette(namedtuple('PaletteData', ['colors', 'transparency'])):
    @classmethod
    def fromfile(cls, palette_file=''):
        with open(palette_file, 'rb') as f:
            data = zlib.decompress(f.read())
        if len(data) != 256 * 4:
            error(f'{palette_file}: palette file size unexpected: {len(data)}')
            return None
        return cls(data[:256 * 3], data[256 * 3:256 * 4])

    def gethash(self, nonce):
        return sha256(self.colors + self.transparency +
                struct.pack('<Q', nonce)).hexdigest()

    def tofile(self, file):
        with open(file, 'wb') as f:
            f.write(zlib.compress(self.colors + self.transparency, level=9))

class RasterModes(enum.Enum):
    P = (1, 1)
    RGB = (2, 3)
    RGBA = (3, 4)
    @property
    def id(self): return self.value[0]
    @property
    def stride(self): return self.value[1]

name_to_modes = RasterModes.__members__
id_to_modes = {v.id: v for v in name_to_modes.values()}

class Raster(namedtuple('Raster', ['size', 'mode', 'data'])):
    __header = struct.Struct('<HHB')

    @classmethod
    def fromfile(cls, raster_file=''):
        with open(raster_file, 'rb') as f:
            data = zlib.decompress(f.read())
        hdr_sz = cls.__header.size
        w, h, mode = cls.__header.unpack(data[:hdr_sz])
        if mode not in id_to_modes:
            error(f'{raster_file}: Invalid mode number: {mode}')
        mode = id_to_modes[mode]
        if len(data) != w * h * mode.stride + hdr_sz:
            error(f'{raster_file}: {mode.name} raster file ({w}x{h}) size unexpected: {len(data)}')
            return None
        return cls((w, h), mode, data[hdr_sz:])

    def tofile(self, file):
        data = type(self).__header.pack(self.size[0], self.size[1],
                self.mode.id) + self.data
        with open(file, 'wb') as f:
            f.write(zlib.compress(data, level=9))

    def gethash(self, nonce):
        return sha256(self.data + struct.pack('<Q', nonce)).hexdigest()

class ImageIndex:
    def __init__(self, cfg = None):
        self.__palettes = {}
        self.__rasters = {}
        if cfg == None: cfg = read_cfg()
        self.__cfg = cfg
        self.__dumpPath = os.path.dirname(cfg['RomPath']) + '/dump'
        self.__files = {}
        self.props = {
            'dumpDir': self.dump_path,
            'idatDir': IMAGEDATA_PATH,
        }

        self.__init_index('sprite')
        self.__init_index('image')

    @property
    def dump_path(self): return self.__dumpPath

    def __init_index(self, dir):
        path = self.__dumpPath + '/' + dir
        if os.path.isdir(path):
            for f in sorted(os.listdir(path)):
                self.__init_index(f'{dir}/{f}')
        elif dir.lower().endswith('.png'):
            info = self.get_image_info(path)
            if info == None: return
            p, r = info
            f = '{dumpDir}/' + dir
            if p != None and p not in self.__palettes:
                self.__palettes[p] = f
            if r not in self.__rasters:
                self.__rasters[r] = f

    def get_palette_ref(self, palette):
        return self.__palettes.get(palette)

    def get_raster_ref(self, raster):
        return self.__rasters.get(raster)

    def set_palette_ref(self, palette, ref):
        self.__palettes[palette] = ref

    def set_raster_ref(self, raster, ref):
        self.__rasters[raster] = ref

    def get_image_info(self, path):
        if path not in self.__files:
            i = Image.open(path)
            try:
                i.load()
            except:
                ImageFile.LOAD_TRUNCATED_IMAGES = True
                warn(f'{path}: Image truncated')
                try:
                    i.load()
                finally:
                    ImageFile.LOAD_TRUNCATED_IMAGES = False

            for name in i.info.keys():
                if name not in ['transparency', 'icc_profile', 'dpi', 'srgb',
                        'Raw profile type exif']:
                    warn(f'{path}: contains unknown metadata field: {name}')

            if i.mode not in name_to_modes:
                warn(f'{path}: invalid image mode: {i.mode}.')
                self.__files[path] = None
                return None

            mode = name_to_modes[i.mode]
            if mode == RasterModes.P:
                trans = i.info.get('transparency', b'\xff'* 256)
                if type(trans) is int:
                    tp = [0xff] * 256
                    tp[trans] = 0
                    trans = bytes(tp)
                p = Palette(bytes(i.getpalette()), trans)
            else:
                assert mode == RasterModes.RGB or mode == RasterModes.RGBA
                if 'transparency' in i.info.keys():
                    warn(f'{path}: contains unknown metadata field: {name}')
                p = None

            r = Raster(i.size, mode, i.tobytes())
            self.__files[path] = (p, r)

        return self.__files[path]

_imageIndex = None
def imageIndex():
    global _imageIndex
    if _imageIndex == None:
        info('Indexing images...')
        _imageIndex = ImageIndex()
        info('Completed indexing images.')
    return _imageIndex

def read_cfg(file=None):
    if file == None:
        file = STAR_ROD_PATH + '/cfg/main.cfg'
    res = OrderedDict()
    try:
        with open(file, 'r') as f:
            for line in f:
                if line.startswith('%'): continue
                key, _, value = line.strip().partition(' = ')
                res[key] = value
    except:
        return {}
    return res

def write_cfg(settings, file=None):
    if file == None:
        file = STAR_ROD_PATH + '/cfg/main.cfg'
    with open(file, 'w') as f:
        f.write('% Auto-generated config file, modify with care.\n')
        for (key, value) in settings.items():
            f.write(f'{key} = {value}\n')

# File extensions that should always be copied
copied_extensions = ['txa', 'xml', 'mtl']

def _expand_images(root_dir, src_dir, patch_dir, path=''):
    if path == '':
        shutil.rmtree(f'{root_dir}/{src_dir}', ignore_errors = True)
        os.makedirs(f'{root_dir}/{src_dir}', exist_ok = True)
    else:
        path += '/'
    for f in sorted(os.listdir(f'{root_dir}/{patch_dir}/{path}')):
        patch_file = f'{root_dir}/{patch_dir}/{path}{f}'
        if os.path.isdir(patch_file): # Make directory in dest
            os.mkdir(f'{root_dir}/{src_dir}/{path}{f}')
            _expand_images(root_dir, src_dir, patch_dir, path + f)
        elif f.lower().rpartition('.')[2] in copied_extensions:
            shutil.copy(patch_file, f'{root_dir}/{src_dir}/{path}')
        elif f.lower() == '_images.json': # For images we do a rough differ
            # Load json file
            with open(patch_file, 'r') as f:
                image_data = json.load(f)

            for (img_file, desc) in image_data.items():
                if desc['palette'] == None:
                    palette_file = None
                else:
                    # Load palette/transparency information
                    palette_file = desc['palette'].format(**imageIndex().props)
                    if palette_file.lower().endswith('.png'):
                        palette = imageIndex().get_image_info(palette_file)[0]
                    else:
                        palette = Palette.fromfile(palette_file)
                        if palette == None:
                            continue

                # Load raster information
                raster_file = desc['raster'].format(**imageIndex().props)
                if raster_file.lower().endswith('.png'):
                    raster = imageIndex().get_image_info(raster_file)[1]
                else:
                    raster = Raster.fromfile(raster_file)
                    if raster == None:
                        continue

                # Create image from palette/raster
                i = Image.new(raster.mode.name, raster.size)
                if raster.mode == RasterModes.P:
                    i.putpalette(palette.colors)
                    i.info['transparency'] = palette.transparency
                i.frombytes(raster.data)
                i.save(f'{root_dir}/{src_dir}/{path}{img_file}')
        else:
            error(f'Unexpected file: {root_dir}/{patch_dir}/{path}{f}' )

def expand_images():
    if not askyesno('Are you sure you want to do this? This WILL clear the ' +
            'entire image and sprite directories!'): return

    image_dirs = [
            ('/sprite/npc', 'src', 'patch'),
            ('/sprite/player', 'src', 'patch'),
            ('/image', 'assets', 'patch/assets'),
            ('/image', 'bg', 'patch/bg'),
            ('/image', 'compressed', 'patch/compressed'),
            ('/image', 'texture', 'patch/texture'),
    ]
    for dir, _, patch_dir in image_dirs:
        if not os.path.isdir(f'{SCRIPT_PATH}{dir}/{patch_dir}'):
            error(f'{dir}/{patch_dir}: not a directory')
            return

    for dir, src_dir, patch_dir in image_dirs:
        _expand_images(SCRIPT_PATH + dir, src_dir, patch_dir)

def _compress_images(root_dir, src_dir = 'src', patch_dir = 'patch', path=''):
    idx = imageIndex()
    if path == '':
        shutil.rmtree(f'{root_dir}/{patch_dir}', ignore_errors = True)
        os.makedirs(f'{root_dir}/{patch_dir}', exist_ok=True)
        os.makedirs(IMAGEDATA_PATH, exist_ok=True)
    else:
        path += '/'
    images = {}

    def getuniqpath(dir, prefix, obj):
        nonce = 0
        curhash = obj.gethash(0)
        while os.path.isfile(dir + '/' + prefix + curhash):
            curhash = obj.gethash(nonce)
            nonce += 1
        return prefix + curhash

    for f in sorted(os.listdir(f'{root_dir}/{src_dir}/{path}')):
        src_file = f'{root_dir}/{src_dir}/{path}{f}'
        if os.path.isdir(src_file):
            # Ignore these directories
            if f.lower() in ['cache', 'temp', 'patch']:
                continue

            # Make directory in patch
            os.mkdir(f'{root_dir}/{patch_dir}/{path}{f}')
            _compress_images(root_dir, src_dir, patch_dir, path + f)
        elif f.lower().rpartition('.')[2] in copied_extensions:
            shutil.copy(src_file, f'{root_dir}/{patch_dir}/{path}')
        elif f.lower().endswith('.png'): # For images we do a rough differ
            info = idx.get_image_info(src_file)
            if info == None:
                error(f'{src_file} ignored because not a valid palette PNG file')
                continue

            p, r = info
            rref = idx.get_raster_ref(r)

            if p != None:
                pref = idx.get_palette_ref(p)
                if pref == None:
                    tmpfile = getuniqpath(IMAGEDATA_PATH, 'palette_', p)
                    p.tofile(f'{IMAGEDATA_PATH}/{tmpfile}')
                    pref = f'{{idatDir}}/{tmpfile}'
                    idx.set_palette_ref(p, pref)
            else:
                pref = None

            if rref == None:
                tmpfile = getuniqpath(IMAGEDATA_PATH, 'raster_', r)
                r.tofile(f'{IMAGEDATA_PATH}/{tmpfile}')
                rref = f'{{idatDir}}/{tmpfile}'
                idx.set_raster_ref(r, rref)

            images[f] = {'raster': rref, 'palette': pref}
        else:
            error(f'Unexpected file: {root_dir}/{src_dir}/{path}{f}' )
    if len(images):
        with open(f'{root_dir}/{patch_dir}/{path}/_images.json', 'w') as f:
            json.dump(images, f, indent=2, sort_keys=True)

def compress_images():
    imageIndex()
    info('Compressing images...')
    image_dirs = [
            ('/sprite/npc', 'src', 'patch'),
            ('/sprite/player', 'src', 'patch'),
            ('/image', 'assets', 'patch/assets'),
            ('/image', 'bg', 'patch/bg'),
            ('/image', 'compressed', 'patch/compressed'),
            ('/image', 'texture', 'patch/texture'),
    ]
    shutil.rmtree(IMAGEDATA_PATH, ignore_errors = True)
    for dir, src_dir, _ in image_dirs:
        if not os.path.isdir(f'{SCRIPT_PATH}{dir}/{src_dir}'):
            error(f'{dir}/{src_dir}: not a directory')
            return

    for dir, src_dir, patch_dir in image_dirs:
        info(f'Compressing images in {dir}/{src_dir}')
        _compress_images(SCRIPT_PATH + dir, src_dir, patch_dir)

def compile_map():
    with open(SCRIPT_PATH + '/map/MapTable.xml') as f:
        data = f.read()

    args = []
    bs = BeautifulSoup(data, 'xml')
    for m in bs.find_all('Map') + bs.find_all('Stage'):
        name = m.get_attribute_list('name')[0]
        args += ['-CompileShape', name, '-CompileHit', name]

    return args

class Job:
    def combine(self, other):
        return False

    def execute(self):
        pass

class StarRodJob:
    def __init__(self, actions = []):
        assert type(actions) == list
        self.__actions = list(actions)

    def combine(self, other):
        if isinstance(other, StarRodJob):
            self.__actions += other.__actions
            return True
        else:
            return False

    def execute(self):
        if len(self.__actions):
            args = ['java', '-jar', STAR_ROD_PATH + '/StarRod.jar']
            args += self.__actions

            cfg = read_cfg()
            cfg_old = OrderedDict(cfg)
            cfg['ModPath'] = SCRIPT_PATH
            write_cfg(cfg)

            try:
                check_call(args)
            finally:
                write_cfg(cfg_old)

class FnJob:
    def __init__(self, fn):
        self.__fn = fn

    def execute(self):
        self.__fn()

copied = False
def copy_assets():
    global copied
    if copied:
        warn('multiple copy_assets will be ignored')
        return None
    copied = True

    cfg = read_cfg()
    args = ['-CopyAssets']
    if not os.path.isfile(cfg['RomPath']):
        error(f'Cannot find ROM at: {cfg["RomPath"]}')
        return []
    if not os.path.isdir(os.path.dirname(cfg['RomPath']) + '/dump'):
        info('We need to dump assets first. Doing it at this point.', show=True)
        args = ['-DumpAssets'] + args

    return StarRodJob(args)

def print_help(maxwidth=70):
    msg = '''{} COMMANDS...

where COMMANDS is a list of commands executed from left to right of the following:
'''.format(sys.argv[0])
    namelen = max(len(name) for name, _, _ in job_descs) + 4
    for name, desc, _ in job_descs:
        msg += '  ' + name.ljust(namelen - 2)
        if namelen > maxwidth // 2:
            desc = '\n'.join(textwrap.wrap(desc, maxwidth - 4))
            msg += '\n' + textwrap.indent(desc, ' ' * 4)
        else:
            desc = '\n'.join(textwrap.wrap(desc, maxwidth - namelen))
            msg += textwrap.indent(desc, ' ' * namelen).strip()
        msg += '\n'

    print(msg)
    quit()

job_descs = [
  ('compile', 'Compile the mod into a *.z64 file. NOTE this does not always ' +
      'compile the map files as well!', lambda: StarRodJob(['-CompileMod'])),
  ('compile-maps', 'Compile all the map files', lambda: StarRodJob(compile_map())),
  ('compress-images', 'Compress image data by referencing our original ' +
      'assets to minimize amount of game assets, writing all compressed ' +
      'data to the /imagedata folder', lambda: FnJob(compress_images)),
  ('copy-assets', 'Copy all the dumped assets into the mod folder (and ' +
      'potentially dumping the mods from the ROM if needed)', copy_assets),
  ('expand-images', 'Expand image data from our patch files to populate the ' +
      'source folders', lambda: FnJob(expand_images)),
  ('help', 'Prints this help message and exits', print_help),
  ('package', 'Packages this mod into a patch file. This should be done ' +
      'after a successful compile.', lambda: StarRodJob(['-PackageMod']) )
]
jobs = {job[0]: job for job in job_descs}

def show_gui():
    root = tk.Tk()

    def do_job(job):
        dlg = tk.Toplevel(root)
        dlg.title('StarRodAux')
        lbl = tk.Label(dlg, text='Running job...')
        lbl.grid(row=0, column=0, padx=40, pady=40)
        dlg.resizable(width=False, height=False)
        dlg.grab_set()
        dlg.transient(root)

        def execute(job):
            try:
                job = job()
                if job != None:
                    job.execute()
            except:
                error('A python error has occurred:\n\n' + traceback.format_exc())
            finally:
                dlg.destroy()
        t = threading.Thread(target=execute, args=(job,))
        t.start()

    row = 0
    for name, _, job in job_descs:
        if name == 'help': continue
        b = tk.Button(root, text=name, width=30, command=partial(do_job, job))
        b.grid(row=row, column=0, padx=10, pady=5)
        row += 1
    root.resizable(width=False, height=False)
    root.mainloop()

def main():
    global STAR_ROD_PATH

    try:
        vers = check_output(['java', '-cp', SCRIPT_PATH + '/auxfiles', 'getvers'])
        if int(vers.partition(b'.')[0]) < 12:
            error('Requires java 12 or later!')
            quit()
    except FileNotFoundError:
        error(f'Unable to find java, did you install it?')
        quit()

    aux_path = f'{SCRIPT_PATH}/auxfiles/main.cfg'
    STAR_ROD_PATH = read_cfg(aux_path).get('STAR_ROD_PATH', '')
    while not os.path.isfile(STAR_ROD_PATH + "/StarRod.jar"):
        if STAR_ROD_PATH:
            error(f'Invalid StarRod path: {STAR_ROD_PATH}')
        if HEADLESS:
            STAR_ROD_PATH = input('Path to StarRod directory: ')
        else:
            messagebox.showinfo(title='StarRodAux',
                    message='Please give the path to StarRod directory')
            res = filedialog.askdirectory(title='Path to StarRod directory')
            if not res: quit()
            STAR_ROD_PATH = res
        write_cfg({'STAR_ROD_PATH': STAR_ROD_PATH}, aux_path)

    cfg = read_cfg()
    if cfg.get('RomPath', 'null') == 'null':
        error('You must run StarRod first to initialize its configurations!')
        quit()

    joblist = []
    if len(sys.argv) <= 1:
        if HEADLESS:
            print_help()
        else:
            show_gui()
    for cmd in sys.argv[1:]:
        if cmd not in jobs:
            error(f'Illegal command: {cmd}')
            quit()
        job = jobs[cmd][2]()
        if job == None: continue
        if len(joblist) == 0 or not joblist[-1].combine(job):
            joblist.append(job)

    for job in joblist:
        job.execute()

if __name__ == '__main__':
    try:
        main()
    except SystemExit:
        pass
    except KeyboardInterrupt:
        print('Interrupted!')
    except:
        error('A python error has occurred:\n\n' + traceback.format_exc())
