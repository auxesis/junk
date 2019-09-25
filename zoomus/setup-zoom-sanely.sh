#!/bin/bash

TARGET=~/Library/Preferences/ZoomChat.plist

### GENERAL

plutil -replace ZoomEnterFullscreenWhenDualMonitorSetted -string false $TARGET

# "Enter full screen when a participant shares their screen"
plutil -replace ZoomEnterFullscreenWhenViewShare -string false $TARGET

# "Prompt a confirmation before leaving a meeting"
plutil -replace ZoomRemindMeWhenLeaveMeeting -string false $TARGET

# "Add Zoom to macOS menu bar"
plutil -replace ZoomShowIconInMenuBar -string false $TARGET

### VIDEO

# "My video: Mirror my video"
plutil -replace ZoomMirrorEffect -string true $TARGET

# "Meetings: Always display participant name on their video"
plutil -replace ZMEnableShowUserName -string true $TARGET

