build default: devel

#------------------------------------------------------------------------------#

.DELETE_ON_ERROR:
.PHONY: devel build default release
VERSION := $(strip $(shell cat VERSION))
SOURCES := $(strip $(sort \
    $(wildcard trace32_cli/*.py) \
    $(shell find capi -type f) \
    rw_assist.c setup.cfg setup.py Makefile LICENSE VERSION \
))

#------------------------------------------------------------------------------#

DEVEL_TARGET := $(strip $(wildcard dist/trace32_cli-$(VERSION)*.whl))
DEVEL_TARGET := $(if $(DEVEL_TARGET),$(DEVEL_TARGET),_develop)
devel: $(DEVEL_TARGET)

$(DEVEL_TARGET):  $(SOURCES)
	rm -rf dist build
	python3 setup.py clean sdist bdist_wheel

#------------------------------------------------------------------------------#

release: dist/trace32-cli-$(VERSION).tar.gz

dist/trace32-cli-$(VERSION).tar.gz: private export RELEASE=1
dist/trace32-cli-$(VERSION).tar.gz: $(SOURCES)
	@if [ "$$(git status --porcelain)" != "" ]; then \
	    echo "error: repo has uncommitted changes/files." >&2 && \
	    echo "Cowardly refusing to generate release build." >&2 && \
	    exit 1; \
	fi
	$(MAKE) build
	ls $@

clean:
	rm -rf dist build

#------------------------------------------------------------------------------#

upload: dist/trace32-cli-$(VERSION).tar.gz
	rm -rf dist build
	$(MAKE) --no-print-directory release
	ls dist/trace32_cli-$(VERSION)-*.whl
	ls dist/trace32-cli-$(VERSION).tar.gz
	twine upload --skip-existing --repository local \
	    dist/trace32_cli-$(VERSION)-*.whl \
	    dist/trace32-cli-$(VERSION).tar.gz
