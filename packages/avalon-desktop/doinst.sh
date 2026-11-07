# avalon-desktop: put Avalon's settings in place over the packages' own, and make sure the login
# screen's user exists. installpkg runs this from the root it installs into: every path here is
# relative to it. The account files are only touched in a complete system (one with root in it):
# liveslak installs each module into a folder of its own, where an etc/passwd made here would hide
# the real one. (avalon-install creates the greeter account on the new system itself.)
mkdir -p etc/mango
cp -f usr/share/avalon/mango/config.conf etc/mango/config.conf
if [ -f etc/passwd ] && grep -q '^root:' etc/passwd && [ -f etc/group ] && grep -q '^root:' etc/group; then
  grep -q '^greeter:' etc/group || echo 'greeter:x:381:' >> etc/group
  grep -q '^greeter:' etc/passwd || echo 'greeter:x:381:381:greetd greeter:/var/lib/greeter:/bin/false' >> etc/passwd
  [ -f etc/shadow ] && { grep -q '^greeter:' etc/shadow || echo 'greeter:*:20000:0:99999:7:::' >> etc/shadow; }
  grep -q '^video:.*greeter' etc/group || sed -i '/^video:/{/:$/s/$/greeter/;/:$/!{/greeter/!s/$/,greeter/}}' etc/group
  mkdir -p var/lib/greeter; chown 381:381 var/lib/greeter 2>/dev/null; chmod 750 var/lib/greeter
fi
