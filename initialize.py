from bs4 import BeautifulSoup
from collections import OrderedDict
from subprocess import check_call
import os
import os.path
import sys

STAR_ROD_PATH = os.getenv('STAR_ROD_PATH')
while not os.path.isfile(STAR_ROD_PATH + "/StarRod.jar"):
    STAR_ROD_PATH = input('Path to star-rod directory: ')

if not os.path.isfile(STAR_ROD_PATH + '/cfg/main.cfg'):
    print('ERROR: you must run StarRod first to initialize its configurations!')

SCRIPT_PATH = os.path.realpath(os.path.dirname(__file__))

# TODO: MAKE SURE StarRod is not running in background

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
  copy-assets      Copy all the dumped assets into the mod folder (and
                   potentially dumping the mods from the ROM if needed)
  help             Prints this help message and exits
  package          Packages this mod into a patch file
""".format(sys.argv[0]))
    quit()


def main():

    args = ['java', '-jar', STAR_ROD_PATH + '/StarRod.jar']
    copied = False
    if len(sys.argv) <= 1:
        help()
    for cmd in sys.argv[1:]:
        if cmd == 'copy-assets':
            if copied:
                print('WARNING: multiple copy_assets will be ignored')
                continue
            args += copy_assets()
            copied = True
        elif cmd == 'compile-maps':
            args += compile_map()
        elif cmd == 'compile':
            args.append('-CompileMod')
        elif cmd == 'package':
            args.append('-PackageMod')
        elif cmd == 'help':
            help()
        else:
            print(f'Illegal command: {cmd}')
            quit()



    cfg = read_cfg()
    cfg_old = OrderedDict(cfg)
    cfg['ModPath'] = SCRIPT_PATH
    write_cfg(cfg)


    try:


        check_call(args)
    finally:
        write_cfg(cfg_old)




if __name__ == '__main__':
    main()
