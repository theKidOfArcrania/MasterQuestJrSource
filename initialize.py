from bs4 import BeautifulSoup
from collections import OrderedDict, namedtuple
from subprocess import check_call
from PIL import Image, ImageFile
from hashlib import sha256
import json
import shutil
import os
import os.path
import sys
import struct
import zlib

STAR_ROD_PATH = os.getenv('STAR_ROD_PATH')
while not os.path.isfile(STAR_ROD_PATH + "/StarRod.jar"):
    STAR_ROD_PATH = input('Path to star-rod directory: ')

if not os.path.isfile(STAR_ROD_PATH + '/cfg/main.cfg'):
    print('ERROR: you must run StarRod first to initialize its configurations!')

SCRIPT_PATH = os.path.realpath(os.path.dirname(__file__))

IMAGEDATA_PATH = f'{SCRIPT_PATH}/imagedata'

# TODO: MAKE SURE StarRod is not running in background

class Palette(namedtuple('PaletteData', ['colors', 'transparency'])):
    @classmethod
    def fromfile(cls, palette_file=''):
        with open(palette_file, 'rb') as f:
            data = zlib.decompress(f.read())
        if len(data) != 256 * 4:
            print(f'ERROR: {palette_file}: palette file size unexpected: {len(data)}')
            return None
        return cls(data[:256 * 3], data[256 * 3:256 * 4])

    def gethash(self, nonce):
        return sha256(self.colors + self.transparency +
                struct.pack('<Q', nonce)).hexdigest()

    def tofile(self, file):
        with open(file, 'wb') as f:
            f.write(zlib.compress(self.colors + self.transparency, level=9))



class Raster(namedtuple('Raster', ['size', 'data'])):
    @classmethod
    def fromfile(cls, raster_file=''):
        with open(raster_file, 'rb') as f:
            data = zlib.decompress(f.read())
        w, h = struct.unpack('<HH', data[:4])
        if len(data) != w * h + 4:
            print(f'ERROR: {raster_file}: raster file ({w}x{h}) size unexpected: {len(data)}')
            return None
        return cls((w, h), data[4:])

    def tofile(self, file):
        data = struct.pack('<HH', self.size[0], self.size[1]) + self.data
        with open(file, 'wb') as f:
            f.write(zlib.compress(data, level=9))

    def gethash(self, nonce):
        return sha256(self.data + struct.pack('<Q', nonce)).hexdigest()

class SpriteIndex:
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

        self.__init_index()

    @property
    def dump_path(self): return self.__dumpPath

    def __init_index(self, dir='sprite'):
        path = self.__dumpPath + '/' + dir
        if os.path.isdir(path):
            for f in sorted(os.listdir(path)):
                self.__init_index(f'{dir}/{f}')
        elif dir.lower().endswith('.png'):
            info = self.get_image_info(path)
            if info == None: return
            p, r = info
            f = '{dumpDir}/' + dir
            if p not in self.__palettes:
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
                print(f'{path}: Image truncated')
                try:
                    i.load()
                finally:
                    ImageFile.LOAD_TRUNCATED_IMAGES = False

            if i.mode != 'P':
                print(f'{path}: not a 8-bit palette image')
                return None

            for name in i.info.keys():
                if name not in ['transparency', 'icc_profile', 'dpi', 'srgb',
                        'Raw profile type exif']:
                    print(f'{path}: contains unknown metadata field: {name}')

            trans = i.info.get('transparency', b'\xff'* 256)
            if type(trans) is int:
                tp = [0xff] * 256
                tp[trans] = 0
                trans = bytes(tp)
            p = Palette(bytes(i.getpalette()), trans)
            r = Raster(i.size, i.tobytes())
            self.__files[path] = (p, r)

        return self.__files[path]

_spriteIndex = None
def spriteIndex():
    global _spriteIndex
    if _spriteIndex == None:
        print('Indexing sprites...')
        _spriteIndex = SpriteIndex()
    return _spriteIndex

def read_cfg():
    res = OrderedDict()
    with open(STAR_ROD_PATH + '/cfg/main.cfg', 'r') as f:
        for line in f:
            if line.startswith('%'): continue
            key, _, value = line.strip().partition(' = ')
            res[key] = value
    return res

def write_cfg(settings):
    with open(STAR_ROD_PATH + '/cfg/main.cfg', 'w') as f:
        f.write('% Auto-generated config file, modify with care.\n')
        for (key, value) in settings.items():
            f.write(f'{key} = {value}\n')

def _expand_sprites(root_dir, path=''):
    if path == '':
        shutil.rmtree(root_dir + '/src', ignore_errors = True)
        os.mkdir(root_dir + '/src')
    else:
        path += '/'
    for f in sorted(os.listdir(root_dir + '/patch/' + path)):
        patch_file = f'{root_dir}/patch/{path}{f}'
        if os.path.isdir(patch_file): # Make directory in dest
            os.mkdir(f'{root_dir}/src/{path}{f}')
            _expand_sprites(root_dir, path + f)
        elif f.lower().endswith('.xml'): # Always copy xml files
            shutil.copy(patch_file, f'{root_dir}/src/{path}')
        elif f.lower() == '_images.json': # For sprite images we do a rough differ
            # Load json file
            with open(patch_file, 'r') as f:
                image_data = json.load(f)

            for (img_file, desc) in image_data.items():
                # Load palette/transparency information
                palette_file = desc['palette'].format(**spriteIndex().props)
                if palette_file.lower().endswith('.png'):
                    palette = spriteIndex().get_image_info(palette_file)[0]
                else:
                    palette = Palette.fromfile(palette_file)
                    if palette == None:
                        continue

                # Load raster information
                raster_file = desc['raster'].format(**spriteIndex().props)
                if raster_file.lower().endswith('.png'):
                    raster = spriteIndex().get_image_info(raster_file)[1]
                else:
                    raster = Raster.fromfile(raster_file)
                    if raster == None:
                        continue

                # Create 8-bit image from palette/raster
                i = Image.new('P', raster.size)
                i.putpalette(palette.colors)
                i.info['transparency'] = palette.transparency
                i.frombytes(raster.data)
                i.save(f'{root_dir}/src/{path}{img_file}')
        else:
            print(f'ERROR: Unexpected file: {root_dir}/patch/{path}{f}' )

def expand_sprites():
    line = input('Are you sure you want to do this? This WILL clear the ' + \
            'entire sprite directory. (y/N) ').upper()
    if line != 'Y' and line != 'YES': return

    sprite_dirs = ['/sprite/npc', '/sprite/player']
    for dir in sprite_dirs:
        if not os.path.isdir(SCRIPT_PATH + dir + '/patch'):
            print(f'ERROR: {dir}/patch: not a directory')
            return

    for dir in sprite_dirs:
        _expand_sprites(SCRIPT_PATH + dir)

def _compress_sprites(root_dir, path=''):
    idx = spriteIndex()
    if path == '':
        shutil.rmtree(root_dir + '/patch', ignore_errors = True)
        os.mkdir(root_dir + '/patch')
        os.makedirs(IMAGEDATA_PATH, exist_ok=True)
    else:
        path += '/'
    sprites = {}

    def getuniqpath(dir, prefix, obj):
        nonce = 0
        curhash = obj.gethash(0)
        while os.path.isfile(dir + '/' + prefix + curhash):
            curhash = obj.gethash(nonce)
            nonce += 1
        return prefix + curhash


    for f in sorted(os.listdir(root_dir + '/src/' + path)):
        src_file = f'{root_dir}/src/{path}{f}'
        if os.path.isdir(src_file) and f.lower() not in ['cache', 'temp']:
            # Make directory in patch
            os.mkdir(f'{root_dir}/patch/{path}{f}')
            _compress_sprites(root_dir, path + f)
        elif f.lower().endswith('.xml'): # Always copy xml files
            shutil.copy(src_file, f'{root_dir}/patch/{path}')
        elif f.lower().endswith('.png'): # For sprite images we do a rough differ
            info = idx.get_image_info(src_file)
            if info == None:
                print(f'ERROR: {src_file} ignored because not a valid palette PNG file')
                continue

            p, r = info
            pref = idx.get_palette_ref(p)
            rref = idx.get_raster_ref(r)

            if pref == None:
                tmpfile = getuniqpath(IMAGEDATA_PATH, 'palette_', p)
                p.tofile(f'{IMAGEDATA_PATH}/{tmpfile}')
                pref = f'{{idatDir}}/{tmpfile}'
                idx.set_palette_ref(p, pref)

            if rref == None:
                tmpfile = getuniqpath(IMAGEDATA_PATH, 'raster_', r)
                r.tofile(f'{IMAGEDATA_PATH}/{tmpfile}')
                rref = f'{{idatDir}}/{tmpfile}'
                idx.set_raster_ref(r, rref)

            sprites[f] = {'raster': rref, 'palette': pref}
        else:
            print(f'ERROR: Unexpected file: {root_dir}/src/{path}{f}' )
    if len(sprites):
        with open(f'{root_dir}/patch/{path}/_images.json', 'w') as f:
            json.dump(sprites, f, indent=2, sort_keys=True)

def compress_sprites():
    spriteIndex()
    print('Compressing sprites...')
    sprite_dirs = ['/sprite/npc', '/sprite/player']
    shutil.rmtree(IMAGEDATA_PATH, ignore_errors = True)
    for dir in sprite_dirs:
        if not os.path.isdir(SCRIPT_PATH + dir + '/src'):
            print(f'ERROR: {dir}/src: not a directory')
            return

    for dir in sprite_dirs:
        _compress_sprites(SCRIPT_PATH + dir)

def copy_assets():
    cfg = read_cfg()
    args = ['-CopyAssets']
    if not os.path.isfile(cfg['RomPath']):
        raise ValueError(f'Cannot find ROM at: {cfg["RomPath"]}')
    if not os.path.isdir(os.path.dirname(cfg['RomPath']) + '/dump'):
        print('We need to dump assets first')
        args = ['-DumpAssets'] + args
    return args

def compile_map():
    with open(SCRIPT_PATH + '/map/MapTable.xml') as f:
        data = f.read()

    args = []
    bs = BeautifulSoup(data, 'xml')
    for m in bs.find_all('Map') + bs.find_all('Stage'):
        name = m.get_attribute_list('name')[0]
        args += ['-CompileShape', name, '-CompileHit', name]

    return args

def help():
    print("""
python {} COMMANDS...

where COMMANDS is a list of commands executed from left to right of the following:
  compile-maps     Compile all the map files
  compile          Compile the mod into a *.z64 file. NOTE this does not always
                   compile the map files as well!
  compress-sprites Compress sprite data by referencing our original assets to
                   minimize amount of game assets, writing to the
                   /sprite/*/patch folders
  copy-assets      Copy all the dumped assets into the mod folder (and
                   potentially dumping the mods from the ROM if needed)
  expand-sprites   Expand sprite data from our patch files to populate the
                   source folders
  help             Prints this help message and exits
  package          Packages this mod into a patch file
""".format(sys.argv[0]))
    quit()

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
            self.__actions += other.__args
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
def do_job(cmd):
    global copied
    if cmd == 'copy-assets':
        if copied:
            print('WARNING: multiple copy_assets will be ignored')
            return None
        copied = True
        return StarRodJob(copy_assets())
    elif cmd == 'compile-maps':
        return StarRodJob(compile_map())
    elif cmd == 'compile':
        return StarRodJob(['-CompileMod'])
    elif cmd == 'compress-sprites':
        return FnJob(compress_sprites)
    elif cmd == 'expand-sprites':
        return FnJob(expand_sprites)
    elif cmd == 'package':
        return StarRodJob(['-PackageMod'])
    elif cmd == 'help':
        help()
    else:
        print(f'Illegal command: {cmd}')
        quit()

def main():
    jobs = []
    if len(sys.argv) <= 1:
        help()
    for cmd in sys.argv[1:]:
        job = do_job(cmd)
        if job == None: continue
        if len(jobs) == 0 or not jobs[-1].combine(job):
            jobs.append(job)

    for job in jobs:
        job.execute()

if __name__ == '__main__':
    main()
