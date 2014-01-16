makeship
========

makeship is a tool for baking custom ships for Starbound.

The idea is to save the tedium of having to manually choose colors for--and write up in the .structure file--each and every combination of foreground/object and background material.  WIth makeship, you instead come up with colors and JSON for individual bits and draw two images--one base image, and an overlay--and it bakes this into a single image and automatically figures out the color and JSON for the combination tiles.

## Dependencies

makeship is written for Python 3 (I have 3.3) and requires PIL/Pillow.
