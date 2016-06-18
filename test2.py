import urllib
from shutil import copyfile
from lxml import etree
from lxml import objectify
from io import BytesIO

#
# This is a very quick-n-dirty bucklet for maven packages (jar and aar)
#


import os.path
import errno
import os
import pprint
import dpath.util
import hashlib

def mavensha1(group, name, version, ar, index=0):
    if index == len(repos):
        return None
    try:
        link = repos[index] + '{0}/{1}/{2}/{1}-{2}.{3}.sha1'.format(group.replace('.', '/'), name, version, ar)
        f = urllib.urlopen(link)
        cksum = f.read()
        int(cksum, 16) # will throw an error if cksum is not a hexadecimal string
        cached_repos[cksum] = repos[index]
        return cksum
    except ValueError:
        return mavensha1(group, name, version, ar, index + 1)

# helper for mkdir -p
def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:  # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise



cached_repos = {}
repos = ['http://repo1.maven.org/maven2/']

def maven_repository(uri):
    repos.append(uri)

def remote_file(**kwargs):
    print 'remote_file ' + kwargs.get('name')

def read_remote_file(url, invalidate_cache=False):
    if url.startswith('local:'):
        return ''
    dir = os.getcwd() + '/buck-out/gen/maven/'

    if not os.path.isdir(os.getcwd() + '/buck-out/'):
        print 'Run script from main dir'
        exit(1)

    mkdir_p(dir)

    sha1 = hashlib.sha1()
    sha1.update(url)
    cksum = sha1.hexdigest()
    cache = dir + cksum

    if os.path.isfile(cache):
        if invalidate_cache:
            os.remove(file)
            return read_remote_file(url)
        else:
            return open(cache, 'r').read()

    rf = urllib.urlopen(url)

    if rf.getcode() == 404:
        lf = open(cache, 'w')
        lf.write('')
        return ''

    content = rf.read()

    lf = open(cache, 'w')
    lf.write(content)
    return content

def mavensha1(group, name, version, ar, index=0):
    global repos
    if index == len(repos):
        return None, None
    try:
        link = repos[index] + '{0}/{1}/{2}/{1}-{2}.{3}.sha1'.format(group.replace('.', '/'), name, version, ar)

        cksum = read_remote_file(link)
        int(cksum, 16) # will throw an error if cksum is not a hexadecimal string
        cached_repos[cksum] = repos[index] # we know it exists in this repo
        return (cksum, repos[index])
    except ValueError:
        return mavensha1(group, name, version, ar, index + 1)

def dmaven(pkg):
    group, name, version = pkg.split(':', 3)
    for ar in ['aar', 'jar']:
        cksum = mavensha1(group, name, version, ar)
        if cksum != None:
            repo = cached_repos[cksum]
            remote_file(
                name = name + '-maven',
                sha1 = cksum,
                url = make_url(repo, group, name, version, ar),
                out = name + '.' + ar,
            )
            if ar == 'aar':
                android_prebuilt_aar(
                    name = name,
                    aar = ':'+name+'-maven',
                    visibility = ['PUBLIC']
                )
            else:
                prebuilt_jar(
                    name = name,
                    binary_jar = ':' + name + '-maven',
                    visibility = ['PUBLIC']
                )

            return
    print('Not found ' + pkg)


class MavenPackage(object):
    """docstring for MavenPackage"""
    packages = []

    def find_matching_package(self, group, name=''):
        if name != '':
            pkg = group + ':' + name
        else:
            pkg = group
        for package in MavenPackage.packages:
            if package.id == pkg:
                return package
        return None

    def __init__(self, pkg, name='', version='', type='primary'):
        if name == '' and version == '':
            group, name, version = pkg.split(':', 3)
            self.group = group
        else:
            self.group = pkg



        self.name = name
        self.version = version
        self.dependencies = []
        self.repository = None
        self.type = type
        self.id = self.group + ':' + self.name
        # walk tree and look for package with same name
        package = self.find_matching_package(self.id)
        if package:
            if package.version != version:
                print 'Duplicate package {0} with different version {1} and {2},'.format(name, version, package.version)
                print '\tdropping {0}#{1}'.format(name, package.version)
                return
            return

        self.find_repository()
        self.build_dependencies()

        MavenPackage.packages.append(self)

    def find_repository(self):
        for ar in ['aar', 'jar']:
            cksum, repo = mavensha1(self.group, self.name, self.version, ar)
            if cksum != None:
                self.repository = repo
                self.checksum = cksum
                self.file_type = ar

                return

    def build_dependencies(self):
        if self.repository == 'local:':
            return

        pom_url = self.get_url('pom')

        pom = read_remote_file(pom_url)

        # If not found, then local dep
        if pom == '':
            self.repository = 'local:'
            return

        project = objectify.fromstring(pom)

        try:
            for dep in project.dependencies.dependency:
                if dep.scope == 'compile':
                    self.dependencies.append(dep.groupId + ':' + dep.artifactId)
                    depPkg = dep.groupId + ':' + dep.artifactId + ':' + str(dep.version)
                    pkg = MavenPackage(depPkg, '', '', 'secondary')
        except AttributeError:
            pass

    def display_tree(self, indent=''):

        print indent + self.id
        for dep in self.dependencies:
            self.find_matching_package(dep).display_tree(indent + '  ')

    def get_url(self, ar):
        return ((self.repository or 'local:')
                    + '{0}/{1}/{2}/{1}-{2}.{3}'.format(
                        self.group.replace('.', '/'),
                        self.name,
                        self.version, ar))




MavenPackage('com.facebook.fresco:fresco:0.11.0').display_tree()
MavenPackage('com.fivehundredpx:greedo-layout:1.0.0').display_tree()
MavenPackage('org.springframework:spring-core:4.0.0.RELEASE').display_tree()