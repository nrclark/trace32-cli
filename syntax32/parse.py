#!/usr/bin/env python3
import re
import os
import json

from collections import OrderedDict


#------------------------------------------------------------------------------#


def read_syntax_file():
    """ Read the practice.uew syntax-completion file, taken from
    t32/practice/syntaxhighlighting/ultraedit/practice.uew. Return the
    known symbols from the file. """

    data = open('practice.uew').read()
    completions = {}

    section_regex = re.compile('^[ \t]*[/][A-Z0-9]+["]', flags=re.M | re.I)
    group_regex = re.compile('([^"]+)"[^\n]*(.*)', flags=re.DOTALL)

    for section in re.split(section_regex, data)[1:]:
        groups = re.match(group_regex, section).groups()

        name = groups[0]
        section = groups[1].strip()
        completions[name] = [x.strip() for x in section.splitlines()]
        completions[name] = [x for x in completions[name] if x]

    completions.pop('PRACTICE')
    completions.pop('Unused')
    completions.pop('Operators')
    completions['TRACE32 Commands'] = completions.pop('Commands TRACE32')
    completions['PRACTICE Commands'] = completions.pop('Commands PRACTICE')
    completions['DIALOG Commands'] = completions.pop('Menu Dialogs')

    fattributes = []
    options = []
    parameters = []

    for line in completions.pop('Format Opt Param'):
        if line[0:1] == "%":
            fattributes.append(line)

        elif line[0:2] == "//":
            options.append(line[0:2].strip())

        elif re.match("[a-z0-9]", line, flags=re.I):
            parameters.append(line)

    completions['FAttributes'] = fattributes
    completions['Options'] = options
    completions['Parameters'] = parameters
    return completions


#------------------------------------------------------------------------------#


def load_helpfiles():
    """ Read the Trace32 helpfile, taken from t32/help.t32. Split it into
    the subfiles that make it up, and return a dict containing all of
    help.t32's component files. """

    data = open('help.t32').read()

    filename_regex = re.compile("^[ \t]*[*]{4,}[^*\n]+[*]{4,}", flags=re.M)
    matches = [x for x in re.finditer(filename_regex, data)]
    start_points = [x.start() for x in matches] + [len(data)]
    helpfiles = OrderedDict()

    for index in range(len(start_points)-1):
        text = data[start_points[index]:start_points[index+1]]
        match_length = matches[index].end() - matches[index].start()
        name = re.sub("(^[* ]+)|([ *]+$)", "", matches[index].group())
        helpfiles[name] = text[match_length:].strip() + "\n"

    return helpfiles


def write_helpfiles(helpfiles):
    """ Take the 'helpfiles' object, and write out all of its individual
    files as separate files on the filesystem. This is intended to make
    for easier debugging. """

    if not os.path.isdir("files"):
        os.makedirs("files")

    for filename in helpfiles:
        with open(f"files/{filename}", "w") as outfile:
            outfile.write(helpfiles[filename])

def parse_index(helpfiles):
    """ Parse a 'helpfiles' object, and split it into a list of 'entries'
    object (which is expected by other functions in this file). """

    lines = [x.strip() for x in helpfiles['_index.txt'].strip().splitlines()]
    lines = [x for x in lines if x]
    entries = [x.split('","') for x in lines]
    result = [tuple([x[0][1:]] + x[1:5] + [x[5][:-1]]) for x in entries]
    return tuple(result)


#------------------------------------------------------------------------------#


def ffuzz_entries(field, value, entries):
    """ Take an 'entries' object and return all entries that have a field
    that matches the value of 'value'. """

    return [x for x in entries if value.lower() in x[field].lower()]

def show_values(field, entries):
    """ Return all unique values of a field in 'entries'. """

    return sorted(set([x[field] for x in entries]))

def filter_entries(field, value, entries):
    """ Return all entries in 'entries' where 'value' has an exact match
    in the right field of the entry. """

    return [x for x in entries if x[field] == value]

#------------------------------------------------------------------------------#

# Analyze all records in entries and pick out the ones that are functions.
# Massage them into a Python-friendly format for easy use in an autocompleter.

def load_functions(entries):
    """ Finds all entries that decribe functions. Take each matching record
    and parse it to create a more formal format. """

    functions = OrderedDict()

    for entry in filter_entries(2, 'function', entries):
        match = re.search('(.*?)[ \t]*[[](.*)[]]', entry[0])
        alias, syntax = match.groups()

        args = re.search("[(](.*)[)]", syntax).groups()[0].split(",")
        if args == ['']:
            args = []

        args = [re.sub('^[\'"](.*)[\'"]$','\\1', x) for x in args]
        fullname = re.sub("[(].*[)]", "", syntax)
        docref = entry[3]

        record = functions.get(fullname)
        if record is None:
            record = {"aliases": set(), "call_args": set(), "docrefs": set()}

        record["aliases"].add(alias)
        record["call_args"].add(tuple(args))
        record["docrefs"].add(docref)

        functions[fullname] = record

    for name in functions:
        functions[name]['call_args'] = tuple(sorted(functions[name]['call_args']))
        functions[name]['aliases'] = tuple(sorted(functions[name]['aliases']))
        functions[name]['docrefs'] = tuple(sorted(functions[name]['docrefs']))

    return functions


#------------------------------------------------------------------------------#


def load_commands(entries, helpfiles):
    """ Finds all entries that decribe commands. Take each matching record
    and parse it to create a more formal format. Note that this is a work-in-
    progress at the time of this writing. """

    command_entries = filter_entries(2, 'command', entries)
    command_entries += filter_entries(2, 'command !' , entries)
    commands = OrderedDict()

    for entry in command_entries:
        cdesc = entry[0]
        docref = entry[3]

        match = re.search('(.*?)[ \t]*[[](.*)[]]', cdesc)
        if match:
            alias, fullname = match.groups()
            if " " in alias:
                alias = None
        else:
            alias = None
            fullname = cdesc

        record = commands.get(fullname)
        if record is None:
            record = {"aliases": set(), "docrefs": set()}

        if alias:
            record["aliases"].add(alias)

        record["docrefs"].add(docref)

        commands[fullname] = record

    for name in commands:
        commands[name]['aliases'] = tuple(sorted(commands[name]['aliases']))
        commands[name]['docrefs'] = tuple(sorted(commands[name]['docrefs']))

    for command in commands:
        helpstrings = set()

        for docref in commands[command]["docrefs"]:
            regex = re.escape(docref) + "[ \t]+H[ \t]+.*?(?=^G[0-9]+[ \t]+H)"
            regex = re.compile(regex, flags=re.M | re.DOTALL)

            for docname in helpfiles:
                matches = re.findall(regex, helpfiles[docname])
                if not matches:
                    continue

                assert len(matches) == 1
                help = re.sub("^[A-Za-z0-9]+[ \t]+", "", matches[0], flags=re.M)
                helpstrings.add(help.strip() + "\n")

        helpstrings = tuple(sorted(helpstrings))
        commands[command]['helpstrings'] = helpstrings

    return commands


#------------------------------------------------------------------------------#


def generate_json():
    """ Parse help.t32 and dump the generated files to the filesystem.  """

    assert os.path.exists("help.t32")
    assert os.path.exists("practice.uew")

    helpfiles = load_helpfiles()
    entries = parse_index(helpfiles)

    functions = load_functions(entries)
    commands = load_commands(entries, helpfiles)

    with open('helpfiles.json', "w") as outfile:
        outfile.write(json.dumps(helpfiles, indent=2))

    with open('entries.json', "w") as outfile:
        outfile.write(json.dumps(entries, indent=2))

    with open('functions.json', "w") as outfile:
        outfile.write(json.dumps(functions, indent=2))

    with open('commands.json', "w") as outfile:
        outfile.write(json.dumps(commands, indent=2))


#------------------------------------------------------------------------------#

generate_json()

"""
Each item in 'entries' contents:

fields:
0: cmd
1: description
2: type
3: docref
4: target
5: unknown_numeric

known types:
[' ',
 'DIALOG subcommand',
 'DIR command',
 'ENTRY command',
 'GLOBALON command',
 'MENU subcommand',
 'ON command',
 'PI subcommand',
 'PP subcommand',
 'PowerProbe subcomman',
 'Term',
 'Var commands',
 'command',
 'command !',
 'company',
 'country',
 'dimension',
 'flash',
 'frequency',
 'function',
 'host',
 'host os',
 'order code',
 'product',
 'voltage']


"""
