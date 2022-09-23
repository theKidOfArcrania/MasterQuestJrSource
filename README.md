# Paper Mario Master Quest Jr

This is where the source code of 1.x Master Quest Jr code lies.

## Getting started

NOTE: This is ONLY tested with star rod 0.5.3. If you change to different versions
beware you **will** have to tweak some code to get it to compile after you copy
in the assets!

First ensure that star rod is installed, and you should set `STAR_ROD_PATH`
environment variable to where the directory to star rod is located. If this is
not set, the initialization script will ask you for the path to star rod. When
running star rod for the first time, you may need to run it first so that it can
initialize the paper mario ROM file. If possible you should dump assets first.

Next, make sure all the python dependencies are installed:
```
pip3 install bs4 pillow lxml
```

Then, when initializing the project, run the following set of commands:
```
python3 initialize.py copy-assets expand-images compile-maps
```

This will first copy all the assets from the dump first, then expand all the
image data diffs when compared to the underlying ROM dump, and then compile all
the map shape/hit objects. This allows us to minimize the amount of assets that
we would have lying in a public repo source tree. If you are queried about
whether to clear the image/sprite directories, select yes at this point (since
the only thing that's removed is dumped data).

NOTE: If you think you have modified any image/sprite assets **make sure** to
run `python3 initialize.py compress-images` early and often so that git can
actually track any changes that you made, since direct changes made i.e. via
StarRod will not affect the git repo. The underlying operation for
compress-images is designed to be idempotent, i.e. running the command multiple
times in quick succession will have no overall effect and would just be
equivalent as if you ran the command only once.

When you want to build everything, you can use star rod GUI or run:
```
python3 initialize.py compile package
```
Which both cases does the exact same thing. Note that compile does not always
compile map objects also.

## Credits
Emperor\_Thamz, Rainchus, JaThePlayer, Brotenko, theKidOfArcrania
