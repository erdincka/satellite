#!/usr/bin/env bash
#
# Copyright (c) 2025 Erdinc Kaya
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
# the Software, and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
# FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
# COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
# IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

# COMPLETE THE SYSTEM START
echo "System initialization started..."
sed -i '1,/This container IP/!d' /usr/bin/init-script # remove the while loop at the end
/usr/bin/init-script

echo "System initialized, starting demo app..."

cd /app

if [ "x$1" == "x" ]; then
    echo "No arguments supplied, starting both simulators"
    nohup uv run hq.py &
    nohup uv run edge.py &
else
    echo "Starting simulator $1"
    nohup uv run $1.py &
fi

tail -f nohup.out # so docker logs will show logs
