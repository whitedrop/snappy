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


# helper to make url
def make_url(repo, group, name, version, ar):
    return repo + '{0}/{1}/{2}/{1}-{2}.{3}'.format(group.replace('.', '/'), name, version, ar)

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


def remote_file(**kwargs):
    print 'remote_file ' + kwargs.get('name', 'whattt?')

def dmaven(pkg):
    group, name, version = pkg.split(':', 3)
    for ar in ['aar', 'jar']:
        cksum, repo = mavensha1(group, name, version, ar)
        if cksum != None:
            remote_file(
                name = normalize_id(pkg) + '-maven',
                sha1 = cksum,
                url = make_url(repo, group, name, version, ar),
                out =  normalize_id(pkg) + '.' + ar,
            )
            # if ar == 'aar':
            #     android_prebuilt_aar(
            #         name = normalize_id(pkg),
            #         aar = ':'+normalize_id(pkg)+'-maven',
            #         visibility = ['PUBLIC']
            #     )
            # else:
            #     prebuilt_jar(
            #         name = normalize_id(pkg),
            #         binary_jar = ':' + normalize_id(pkg) + '-maven',
            #         visibility = ['PUBLIC']
            #     )

            return
    print('Not found ' + pkg)

def normalize_id(id):
    return id.replace('.', '_').replace(':', '__')

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
        self.normalized_id =  normalize_id(self.id)
        self.package = self.group + ':' + self.name + ':' + self.version
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

    def get_flat_dependencies(self):
        dep_list = []
        self.get_flat_dependencies2(dep_list)
        return list(set(dep_list))

    def get_flat_dependencies2(self, dep_list):
        dep_list.append(self.normalized_id)
        for dep in self.dependencies:
            self.find_matching_package(dep).get_flat_dependencies2(dep_list)
        return

    def register_package(self):
        dmaven(self.package)

    def get_url(self, ar):
        return ((self.repository or 'local:')
                    + '{0}/{1}/{2}/{1}-{2}.{3}'.format(
                        self.group.replace('.', '/'),
                        self.name,
                        self.version, ar))

def find_matching_package_by_name(name):
    for package in MavenPackage.packages:
        if package.name == name:
            return package
    return None

def register_packages_and_dependencies():
    for pkg in MavenPackage.packages:
        pkg.register_package()

def add_libs(input):
    return '//libs:' + input

def get_deps(deps):
    result = []
    for dep in deps:
        if dep.startswith('//mvn:'):
            result.extend(map(add_libs, find_matching_package_by_name(dep[6:])
                                            .get_flat_dependencies()))
        else:
            result.append(dep)
    return result


maven_repository('https://github.com/500px/greedo-layout-for-android/raw/master/releases/')

fresco = MavenPackage('com.facebook.fresco:fresco:0.11.0')
# fresco.display_tree()
# MavenPackage('com.fivehundredpx:greedo-layout:1.0.0').display_tree()
# MavenPackage('org.springframework:spring-core:4.0.0.RELEASE').display_tree()
register_packages_and_dependencies()
print get_deps(['//mvn:fresco', '//res:res'])
