#!/usr/bin/env python3
#########################################################################
# Copyright (c) 2014 Angryoptimist
# 
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
# 
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE X CONSORTIUM BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#########################################################################
import json, collections, re, sys, os
from functools import reduce
from PIL import Image,ImageDraw

# A little decorator for handing fname/file-like-object type arguments;
# for when you want to accept either, but really need a file-like-object.
def fparg(pos_or_key, mode):
    """
    Ensures that a positional or keyword argument to a function is
    opened as a file, if it is a string.
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            if isinstance(pos_or_key, str):
                if isinstance(args[pos_or_key], str):
                    with open(kwargs[pos_or_key], mode) as fp:
                        kwargs[pos_or_key]=fp
                        return func(*args, **kwargs)
                else:
                    return func(*args, **kwargs)
            elif isinstance(pos_or_key, int):
                args=list(args)
                if isinstance(args[pos_or_key], str):
                    with open(args[pos_or_key], mode) as fp:
                        args[pos_or_key]=fp
                        func(*args, **kwargs)
                else:
                    return func(*args, **kwargs)
        return wrapper
    return decorator

class UnexpectedBlockError(Exception):
    def __init__(self, color, found_in=None):
        self.color = color
        self.found_in = found_in
    def __str__(self):
        if found_in != None:
            return "Unexpected color " + \
                   "%s found in %s"%(str(self.color),self.found_in)
        else:
            return "Unexpected color %s"%str(self.color)

###############################################################
# This was the best way I could find to make it selectively   #
# indent arrays nicely.                                       #
# If you've got a better way to do this that doesn't involve  #
# ugliness like regexing JSON output, feel free to change it. #
###############################################################
class SelectiveIndentEncoder(json.JSONEncoder):
    def default(self, obj):
        return (repr(obj) if isinstance(obj, Inline) else \
                json.JSONEncoder.default(self, obj))

class Inline(object):
    def __init__(self, value):
        self.value = value
    def __repr__(self):
        if not isinstance(self.value, (list,tuple)):
            return repr(self.value)
        else:
            return '['+', '.join(map(str,self.value))+']'

def write_structure(structure, outfile):
    json_string=json.dumps(structure,
                           cls=SelectiveIndentEncoder,
                           sort_keys=True, indent=4)
    json_string = re.sub(r'"(\[[^\]]+\])"', r"\1", json_string)
    outfile.write(json_string)

def fix_indent_block(block):
    block['value'] = Inline(tuple(block['value']))
    return block

def read_structure(infile):
    structure = json.load(infile)
    structure['blockKey'] = map(fix_indent_block, structure['blockKey'])
    return structure
###############################################################
###############################################################

def find_pixel(im, color):
    """
    A slow and ridiculous function for getting a pixel of a particular color.

    Intended only for debugging/exceptions.
    """
    for x in range(im.size[0]):
        for y in range(im.size[1]):
            if color[:3] == im.getpixel((x,y))[:3]:
                return (x,y)

def color_tuple(color):
    """
    Turns HTML color values like #FADFAD into rgb tuples.
    """
    return int(color[1:3],16),int(color[3:5],16),int(color[5:7],16)

def alpha_blend(base_color, overlay_color, opacity=0.5):
    """
    Takes two (opaque) colors and blends them, assuming
    full opacity for the base color and an opacity set
    by the argument `opacity` for the overlay color.
    """
    to_float = lambda x : x/255
    to_int = lambda x : int(round(x * 255))
    r,g,b=list(map(to_float, base_color))
    ro,go,bo=list(map(to_float, overlay_color))
    rn = to_int(ro*opacity + r*(1-opacity))
    gn = to_int(go*opacity + g*(1-opacity))
    bn = to_int(bo*opacity + b*(1-opacity))
    return (rn, gn, bn)

def merge_blocks(bblock, oblock):
    nblock = bblock.copy()
    nblock.update(oblock)
    # Wrapping the value in an inline here to preserve decent
    # indenting on output.
    nblock['value'] = Inline(alpha_blend(bblock['value'].value,
                                         oblock['value'].value))
    if 'backgroundMat' in bblock:
        nblock['backgroundMat'] = bblock['backgroundMat']
    if 'object' in oblock:
        nblock['foregroundBlock']=False
        if 'foregroundMat' in nblock:
            print("WARNING:  trying to put an object where there's a foreground")
    if 'comment' in oblock and 'comment' in bblock:
        nblock['comment'] = oblock['comment']+" on "+bblock['comment']
    else:
        try:
            rcomment=" on "+bblock['comment']
        except KeyError:
            try:
                rcomment=" on "+str(bblock['backgroundMat'])
            except KeyError:
                rcomment=" on "+str(bblock['value'])
        try:
            lcomment=oblock['comment']
        except KeyError:
            try:
                lcomment=str(oblock['object'])
            except KeyError:
                try:
                    lcomment=str(oblock['foregroundMat'])
                except KeyError:
                    lcomment=str(oblock['value'])
        nblock['comment']=lcomment+rcomment
    return nblock

def build_ops(base,overlay):
    """
    Sorts all the pixels we need to blend into groups and returns
    that so that we can do every example of each combination at once.
    """
    ops={}
    for x in range(overlay.size[0]):
        for y in range(overlay.size[1]):
            ocolor = overlay.getpixel((x,y))
            if ocolor[3] != 0:
                ocolor = ocolor[:3]
                if ocolor not in ops:
                    ops[ocolor]={}
                bcolor = base.getpixel((x,y))[:3]
                if bcolor not in ops[ocolor]:
                    ops[ocolor][bcolor] = [(x,y)]
                else:
                    ops[ocolor][bcolor].append((x,y))
    return ops

def do_ops(ops, colors, base, overlay):
    """
    Blends pixels and writes it all to a new image, inserting
    new combination blocks into `colors` as it does that.
    """
    new = base.copy()
    draw = ImageDraw.Draw(new, "RGBA")
    for ocolor in ops:
        for bcolor in ops[ocolor]:
            # This doesn't work, so we need to do alpha blending ourselves:
            #draw.point(ops[ocolor][bcolor], fill=ocolor+(128,))
            nblock = merge_blocks(colors[bcolor], colors[ocolor])
            ncolor = nblock['value'].value
            # TODO: Generate new, non-clobbering color instead of complaining
            if ncolor in colors:
                print("UH-OH: a composite block is" + \
                      " clobbering a base block! (%s)"%str(ncolor))
                if ncolor == bcolor:
                    print("ACTUALLY:  it looks like the color didn't change...")
            draw.point(ops[ocolor][bcolor], fill=ncolor)
            colors[ncolor] = nblock
    return new

@fparg(0, 'r')
@fparg(3, 'w')
def make_ship(srcjson_fp, base_fp, overlay_fp, outjson_fp, combined_fp,
              add_json={}):
    structure = read_structure(srcjson_fp)
    structure.update(add_json)
    base = Image.open(base_fp)
    overlay = Image.open(overlay_fp)
    # It's useful to have each block in a dict with their color as the key
    try:
        blocks = dict(map(lambda x : (x['value'].value, x),
                          structure['blockKey']))
    except TypeError:
        if structure == None:
            print("structure is none")
        raise
    # Maybe wrap this in a try at some point
    validate_source(blocks, base, overlay)
    # The magic happens here
    combined = do_ops(build_ops(base, overlay), blocks, base, overlay)
    # Let's scrub unusued block entries (such as entries that only exist to
    # to be combined with other ones.
    combined_colors = list(map(lambda x:tuple(x[1][:3]), combined.getcolors()))
    structure['blockKey'] = list(filter(
        lambda x : tuple(x['value'].value) in combined_colors,
        blocks.values()))
    combined.save(combined_fp)
    # Maybe also wrap this in a try at some point
    validate_build(structure, combined)
    write_structure(structure, outjson_fp)

def validate_build(structure, im):
    scolors=list(map(lambda x : tuple(x['value'].value[:3]),
                 structure['blockKey']))
    icolors=list(map(lambda x : tuple(x[1][:3]), im.getcolors()))
    for c in icolors:
        if c not in scolors:
            raise UnexpectedBlockError(
                    c, 'result image %s'%str(find_pixel(im, c)))

def validate_source(blocks, base, overlay):
    ocolors=list(map(lambda x : tuple(x[1][:3]), 
                     filter(lambda x : x[1][3] != 0, overlay.getcolors())))
    bcolors=list(map(lambda x : tuple(x[1][:3]), base.getcolors()))
    for ocolor in ocolors:
        if ocolor not in blocks:
            raise UnexpectedBlockError(ocolor, 'overlay')
    for bcolor in bcolors:
        if bcolor not in blocks:
            raise UnexpectedBlockError(bcolor, 'base image')

###############################################################

def main():
    import argparse
    def filename(fname):
        if not os.path.isfile(fname):
            raise argparse.ArgumentTypeError(
                    "'%s' is not a regular file"%fname)
        return fname
    def writeable(path):
        full_path = os.path.dirname(os.path.realpath(os.abspath(path)))
        if not os.access(full_path, os.W_OK):
            raise argparse.ArgumentTypeError(
                    "'%s' is not writable"%path)
        return path
    parser = argparse.ArgumentParser(description='Make a ship.')
    parser.add_argument('--infile', help='input .structure file',
                        required=True, type=filename,
                        metavar="STRUCTURE")
    parser.add_argument('--base', help='base image filename',
                        required=True, type=filename,
                        metavar="IMAGE FILE")
    parser.add_argument('--overlay', help='overlay image filename',
                        required=True, type=filename,
                        metavar="IMAGE FILE")
    parser.add_argument('--outfile', help='output .structure file',
                        default='dropship.structure',
                        metavar="WRITEABLE")
    parser.add_argument('--combined', help='blended output image file',
                        default='dropship.png',
                        metavar="WRITEABLE")
    args = parser.parse_args()
    make_ship(args.infile, args.base, args.overlay,
              args.outfile, args.combined,
              add_json={'blockImage' : os.path.basename(args.combined)})

if __name__ == '__main__':
    main()
    #if len(sys.argv) > 1:
    #    main()
    #else:
    #    print("TODO: Implement GUI.")
