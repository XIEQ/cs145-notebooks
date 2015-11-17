# Copyright (c) 2015 Vivek Jain
#
# Released under the MIT license:
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
#
# Author: Vivek Jain (vivek@vivekja.in)
#
# A script to extract the relevant answers from ipynb files and create a
# submission_template.txt file for CS 145 submission. Given an IPython file that
# is written in an expected format (see PROBLEM_PREFIX/TITLE_PREFIX/PART_PREFIX
# below), and answers that are annotated in a particular way (run with -h for
# more details), this should be able to automatically generate the appropriate
# XML.

import argparse
import distutils.util
import json
import os
import re
import sys
import xml.etree.ElementTree as etree

SUBMISSION_FNAME = 'submission_template.txt'
SUPPORTED_NBFORMAT_VERSION = 4
# Map cell type -> possible prefixes for an answer.
# Make sure to keep this in sync with the ArgumentParser description!
ANSWER_PREFIX = {
  'code': [
    '%%sql\n-- ANSWER\n',   # Multiline SQL
    '%sql /* ANSWER */',  # Single line SQL
    '# ANSWER\n',           # Python
  ],
  'markdown': ['ANSWER']
}
PROBLEM_PREFIX = r'Problem (\d+)(:.*)?\n-+'
TITLE_PREFIX = r'(.+?)\n-+'
PART_PREFIX = r'### Part \((\w+)\)'
SUBPART_PREFIX = r'#### Part \(([\w.]+)\)'
BUG_MSG = "If you think you've found a bug in this script, please report it! Email vsjain@stanford.edu (but don't include any PS answers since I'm a fellow student in the class)."

# Yay global variables. How I've missed you.
class state:
  current_problem = None
  current_part = None
  did_update_part = False  # Last matched regex was PART_PREFIX
  answer_numbers = set()

# Based on http://stackoverflow.com/a/287944
class colors:
    GREY = '\033[90m'
    RED = '\033[91m'
    ENDC = '\033[0m'


def main():
  parser = argparse.ArgumentParser(
      description="""A script to extract the relevant answers from ipynb files
          and create a submission_template.txt file in the current directory for
          CS 145 submission. Answers are expected to be annotated with the
          following possible prefixes: '%%sql\\n-- ANSWER' (multiline SQL, where
          the \\n represents a newline), '%sql /* ANSWER */' (single line SQL),
          '# ANSWER' (Python) or 'ANSWER' (Markdown).""",  # Make sure to keep this in sync with ANSWER_PREFIX!
      epilog=BUG_MSG)
  parser.add_argument('file', help='The IPython notebook file')
  parser.add_argument('--version', action='version', version='%(prog)s 1.0')
  nb_fname = parser.parse_args().file

  try:
    extract_file(nb_fname)
  except KeyboardInterrupt:
    sys.exit('\n')

def extract_file(nb_fname):
  with open(nb_fname) as nb_file:
    nb = json.load(nb_file)

    if nb['nbformat'] != SUPPORTED_NBFORMAT_VERSION:
      exit('unexpected notebook format version: {} (expected {})'.format(
          nb['nbformat'], SUPPORTED_NBFORMAT_VERSION))

    answers = get_answers(nb)
    confirm_answers(answers)
    write_answers(answers)

def get_answers(nb):
  answers = []

  for cell_type, source in get_cells(nb):
    answer = get_answer(cell_type, source)
    if answer:
      number = get_current_answer_number()
      if number in state.answer_numbers:  # We've already got an answer for this number
        # Print out what the two conflicting answers are
        print answers[-1][1]
        print '\n{}and{}\n'.format(colors.GREY, colors.ENDC)
        print answer
        print
        exit('multiple answers (listed above) found for {}'.format(number))
      else:
        answers.append((number, answer))
        state.answer_numbers.add(number)

    elif cell_type == 'markdown':
      # Some hacky heuristics to try to figure out when we have a new problem/part
      update_current_state(source)

  # A check for the final answer
  check_for_answer()
  return answers

def get_cells(nb):
  for cell in nb['cells']:
    source = ''.join(cell['source'])
    yield cell['cell_type'], source.encode('utf-8')

def get_answer(cell_type, source):
  """Return the source (with prefix removed) if it starts with a valid ANSWER_PREFIX, otherwise return None."""
  if cell_type in ANSWER_PREFIX:
    for prefix in ANSWER_PREFIX[cell_type]:
      if source.startswith(prefix):
        actual_source = source[len(prefix):].strip()  # Remove the prefix
        return actual_source
  return None

def get_current_answer_number():
  """Converts current_problem and current_part into an answer number for the submission template."""
  if state.current_problem is None:
    exit("found an answer that seems to appear before any problem")
  number = state.current_problem
  if state.current_part:
    number += state.current_part
  return number

def exit(msg, is_error=True):
  if is_error:
    msg = '{}Error - {}. {}'.format(colors.RED, msg, colors.ENDC)
  else:
    msg += '. '
  # Print msg in red, BUG_MSG in normal colors
  sys.stderr.write(msg)
  sys.exit("{}".format(BUG_MSG))

def update_current_state(source):
  # print source
  match = re.match(PROBLEM_PREFIX, source)
  if match:
    problem = match.group(1)
  else:
    match = re.match(TITLE_PREFIX, source)
    if match:
      problem = match.group(1)
      problem = problem.lower().replace(' ', '_')
      problem = re.sub(r'(\w*).*', r'\1', problem)  # Remove everything after any non-word characters
  if match:
    check_for_answer()
    state.current_problem = problem
    state.current_part = None
    return

  match = re.match(PART_PREFIX, source)
  if match:
    # Moving to a new part of the problem. Must call this before modifying state.did_update_part
    check_for_answer()
    state.did_update_part = True
    part = match.group(1)
  else:
    match = re.match(SUBPART_PREFIX, source)
    if match:
      check_for_answer(True)
      state.did_update_part = False
      part = match.group(1)
      part = part.replace('.', '_')
  if match:
    assert state.current_problem is not None
    state.current_part = part

def check_for_answer(subpart=False):
  if state.current_problem is None or state.current_part is None:
    return
  number = get_current_answer_number()
  if state.did_update_part and subpart:
    if number in state.answer_numbers:
      exit('answer found for part {} even though it has subparts - this should not be the case'.format(number))
  elif number not in state.answer_numbers:
    exit("no answer found for {}. Please ensure you have an answer, even if it is empty. Run 'python {} -h' for instructions on how answers should be formatted to be detected by this script".format(number, sys.argv[0]))

def confirm_answers(answers):
  for number, answer in answers:
    print colors.GREY + number + ':' + colors.ENDC
    print answer
    print

  print '-' * 10
  print 'Please verify the that all of your answers were extracted correctly above.',
  print colors.RED + 'NOTE: the TAs will not be responsible for debugging any errors in extraction by this script.' + colors.ENDC
  response = confirm('Were the above answers extracted correctly?')
  if not response:
    exit('Aborting', is_error=False)

def confirm(prompt):
  while True:
    try:
      response = distutils.util.strtobool(raw_input(prompt + ' [y/n] '))
      return response
    except ValueError:
      print 'Invalid input, please try again'

def write_answers(answers):
  name = raw_input('Full name: ')
  sunet = raw_input('SUNet ID (NOT your student ID number!): ')

  if os.path.exists(SUBMISSION_FNAME):
    confirm('{} already exists. Do you want to overwrite it? '.format(SUBMISSION_FNAME))

  # We generate XML with raw strings...because I want a very specific format
  # with the correct whitespace.
  indent = ' ' * 4
  output = '<?xml version="1.0"?>\n'
  output += '<pset>\n'
  output += indent + '<student>\n'
  output += '{0}<name>\n{1}\n{0}</name>\n'.format(indent * 2, indent * 3 + name)
  output += '{0}<sunet>\n{1}\n{0}</sunet>\n'.format(indent * 2, indent * 3 + sunet)
  output += indent + '</student>\n\n'
  for number, answer in answers:
    output += '{0}<answer number="{2}">\n{1}<![CDATA[\n{3}\n{1}]]>\n{0}</answer>\n'.format(indent, indent * 2, number, answer)

  output += '</pset>\n'

  try:
    # Ensure we actually generated valid XML
    etree.fromstring(output)
  except etree.ParseError:
    exit('unexpected error generating XML')

  with open(SUBMISSION_FNAME, 'wb') as f:
    f.write(output)

  print "Extracted answers to {}. You should verify that the output file is as you expect. Don't forget to submit!".format(SUBMISSION_FNAME)

if __name__ == '__main__':
  main()
