ARCHIVE := misc-api-capi_20210615170802_all_files.zip
ARCHIVE_URL := https://www.lauterbach.com/scripts/misc/api~capi/$(ARCHIVE)

#------------------------------------------------------------------------------#

all: hotwire
distclean:: clean
unpack: capi/src/t32.h

hotwire: trace32_cli/t32api_errors.py trace32_cli/VERSION
hotwire: trace32_cli/_t32api.so

#------------------------------------------------------------------------------#

$(ARCHIVE):
	curl $(ARCHIVE_URL) -o $(@)
	touch -c $@

download: $(ARCHIVE)

distclean::
	rm -f $(ARCHIVE)

.SECONDARY: $(ARCHIVE)

#------------------------------------------------------------------------------#

capi/release.txt: $(ARCHIVE)
	rm -rf $(dir $@) && mkdir -p $(dir $@)
	cd $(dir $@) && unzip $(abspath $(ARCHIVE))
	find $(dir $@) -type f | xargs file | sort | grep -iv text | \
	    sed 's/:.*//g' | xargs -r rm
	find $(dir $@) -type f | xargs -r file | grep -i text | sed 's/:.*//g' | \
	    xargs -r -n1 -P1 dos2unix
	find $(dir $@) -type f | xargs touch -c

capi/src/t32.h: capi/release.txt;

clean::
	rm -rf capi

#------------------------------------------------------------------------------#

LIB_SOURCES := capi/src/hremote.c capi/src/t32nettcp.c capi/src/tcpsimple2.c
LIB_SOURCES += rw_assist.c

build: trace32_cli/_t32api.so

%.o: private CC = gcc
%.o: private CFLAGS ?= -O2 -Wall -Wextra -pedantic -MMD -MP

%.o: %.c
	$(CC) $(CFLAGS) $< -fPIC -shared -c -o $@

rw_assist.o: private CFLAGS += -I capi/src

-include $(shell find capi/ -type f -name '*.d' 2>/dev/null)
-include rw_assist.d

$(patsubst %.c,%.o,$(filter capi/src/%,$(LIB_SOURCES))): \
	private CFLAGS += -DENABLE_NOTIFICATION -Wno-missing-field-initializers

.INTERMEDIATE: $(patsubst %.c,%.o,$(LIB_SOURCES))
.SECONDARY: $(filter capi/src/%,$(LIB_SOURCES))

trace32_cli/_t32api.so:  $(patsubst %.c,%.o,$(LIB_SOURCES))
	$(CC) $(CFLAGS) $^ -shared -o $@

clean::
	rm -f _t32api.so
	rm -f $(patsubst %.c,%.o,$(LIB_SOURCES))
	rm -f $(patsubst %.c,%.d,$(LIB_SOURCES))

#------------------------------------------------------------------------------#

trace32_cli/t32api_errors.py: setup.py capi/src/t32.h
	python3 -c 'from setup import generate_errfile; generate_errfile()'

trace32_cli/VERSION: VERSION
	printf "$$(cat $<)-HOTWIRE" >$@

clean::
	rm -f trace32_cli/t32api_errors.py
	rm -f trace32_cli/VERSION
