# Paper Mario Master Quest Jr

This is where the source code of 1.x Master Quest Jr code lies.

## Getting started

NOTE: This is ONLY tested with star rod 0.5.3. If you change to different versions
beware you **will** have to tweak some code to get it to compile after you copy
in the assets!

Make sure you have [java >=12](https://adoptopenjdk.net/) installed on your
machine. You will have to run StarRod first to get its settings initialized
(with a ROM/mod directory selected)!

When running staraux for the first time, you might be queried about where
StarRod is installed. Make sure you select the directory corresponding to the
StarRod installation location.

### For windows users
Run `staraux.exe`, which should bring a GUI frontend similar to StarRod, with a
few additional options:
  1. Select **copy-assets**. This command, similar to the StarRod's
     corresponding command, copies all the dumped assets from the ROM into our
     mod directory.
  2. Select **expand-images**. This command will take our compressed image data
     and expand those out to what StarRod would expect. This allows us to
     further minimize the amount of assets that we would have lying in a public
     repo source tree. If you are queried about whether to clear the
     image/sprite directories, **select yes** at this point (since the only
     thing that's removed is dumped data).
  3. Select **compile-maps**. This will compile all the map shape/collision
     data.

Note that `staraux.exe` is created by running
```
pyinstaller --onefile staraux.py
```

### For linux/mac users
First make sure that all the python is installed, and the needed dependencies
are installed as well:
```
pip3 install bs4 pillow lxml
```

Then, when initializing the project, run the following set of commands:
```
python3 staraux.py copy-assets expand-images compile-maps
```

## Contributing to image assets
When you want to modify an image asset, whether that be an image or a sprite,
you MUST recompress all images by running the `compress-images` command in
staraux. Otherwise, git WILL NOT know that you modified some image asset!

You can run the compression command as much as you want. TAKE ADVANTAGE OF THIS.
In fancy terms, the command is designed to be idempotent, which means running it
multiple times in quick succession generally can be the same behavior as if you
just ran it once only.

## Contributing to map data
If you tried to modify some map, you MUST recalculate the map collision/shape
data, either in StarRod or staraux. Otherwise, the resulting shape/collision
data may not be up-to-date when you compile the mod.

## Credits
Emperor\_Thamz, Rainchus, JaThePlayer, Brotenko, theKidOfArcrania
