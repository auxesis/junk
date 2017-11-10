#!/bin/bash

rm montage*.png
montage -tile 9x7 -geometry 128x128 avatars/* montage.png
open montage.png
