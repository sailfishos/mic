Name:       mic
Summary:    Image Creator for Linux Distributions
Version:    1.0.0
Release:    1
Group:      System/Base
License:    GPLv2
BuildArch:  noarch
URL:        http://www.tizen.org
Source0:    %{name}-%{version}.tar.bz2
Source1:    mic.conf
Requires:   util-linux
Requires:   coreutils
Requires:   python3-base >= 3.8
Requires:   e2fsprogs
Requires:   dosfstools >= 2.11-8
Requires:   syslinux >= 3.82
Requires:   kpartx
Requires:   parted
Requires:   device-mapper
Requires:   cpio
Requires:   gzip
Requires:   bzip2
Requires:   zip
Requires:   gnu-tar
Requires:   python3-urlgrabber >= 4.1.0+git1
Requires:   squashfs-tools >= 4.0
Requires:   btrfs-progs
Requires:   python3-distro
Requires:   python-m2crypto
Requires:   python3-zypp >= 0.7.5
Requires:   rpm-python
Requires:   psmisc
Requires:   python3-pykickstart
BuildRequires:  python3-devel
BuildRequires:  python3-setuptools
BuildRoot:  %{_tmppath}/%{name}-%{version}-build

%description
The tool mic is used to create and manipulate images for Linux distributions.
It is composed of three subcommand\: create, convert, chroot. Subcommand create
is used to create images with different types; subcommand convert is used to
convert an image to a specified type; subcommand chroot is used to chroot into
an image.


%package livecd
Summary:    %{name} - livecd imager plugin
Group:      System/Base
Requires:   %{name} = %{version}-%{release}
Requires:   %{name} = %{version}
Requires:   /usr/bin/genisoimage
Requires:   isomd5sum

%description livecd
%{summary}.

%package liveusb
Summary:    %{name} - liveusb imager plugin
Group:      System/Base
Requires:   %{name} = %{version}-%{release}
Requires:   %{name}-livecd = %{version}

%description liveusb
%{summary}.

%package yum
Summary:    %{name} - yum backend plugin
Group:      System/Base
Requires:   %{name} = %{version}-%{release}
Requires:   %{name} = %{version}
Requires:   yum >= 3.2.24

%description yum
%{summary}.

%prep
%setup -q -n %{name}-%{version}

%build
%{py3_build}

%install
rm -rf $RPM_BUILD_ROOT
%{py3_install}

# install our mic.conf
mkdir -p %{buildroot}/%{_sysconfdir}/%{name}
install -m644 %{SOURCE1} %{buildroot}/%{_sysconfdir}/%{name}/%{name}.conf

%files
%defattr(-,root,root,-)
%doc README.rst
%dir %{_sysconfdir}/%{name}
%config(noreplace) %{_sysconfdir}/%{name}/%{name}.conf
%{python3_sitelib}/*
%dir %{_prefix}/lib/%{name}
%dir %{_prefix}/lib/%{name}/plugins
%dir %{_prefix}/lib/%{name}/plugins/*
%{_prefix}/lib/%{name}/plugins/backend/zypppkgmgr.*
%{_prefix}/lib/%{name}/plugins/imager/fs_plugin.*
%{_prefix}/lib/%{name}/plugins/imager/loop_plugin.*
%{_prefix}/lib/%{name}/plugins/imager/raw_plugin.*
%{_bindir}/*

%files livecd
%defattr(-,root,root,-)
%{_prefix}/lib/%{name}/plugins/imager/livecd_plugin.*

%files liveusb
%defattr(-,root,root,-)
%{_prefix}/lib/%{name}/plugins/imager/liveusb_plugin.*

%files yum
%defattr(-,root,root,-)
%{_prefix}/lib/%{name}/plugins/backend/yumpkgmgr.*
