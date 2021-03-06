#!/bin/sh
# Copy BiscuitWM
cp src/biscuitwm.py /usr/bin/biscuitwm.py
cp assets/biscuitwm /usr/bin/biscuitwm
# Copy session entries
cp assets/biscuitwm-session /usr/bin/biscuitwm-session
cp assets/biscuitwm-session.desktop /usr/share/xsessions/biscuitwm-session.desktop
# Create config folder
mkdir /etc/biscuitwm
cp assets/biscuitwm.json /etc/biscuitwm/biscuitwm.json
# Set permissions
chmod a+x /usr/bin/biscuitwm
chmod a+x /usr/bin/biscuitwm-session
