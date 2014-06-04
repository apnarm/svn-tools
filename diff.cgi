#!/usr/bin/env python
"""

This CGI script shows SVN diffs in HTML format. It can show local changes,
or differences between trunk and a specified branch.

Example URL to show local changes:
    /diff/

Example URL to show differences between a branch and trunk:
    /diff/?path=^/branches/dogs

Example Apache configuration:
---------------------------------------------------------

Alias /diff/ /home/rbutcher/svn-tools/diff.cgi
<Location "/diff/">
    SetHandler cgi-script
    Options ExecCGI
    SetEnv LANG "en_AU.UTF8"
    SetEnv SVN_ROOT "/home/rbutcher/project/checkout/"
    SetEnv SVN_URL_ROOT "svn://svn.local/project/"
    SetEnv LINK_ROOT "http://trac.local/project/browser/"
</Location>

---------------------------------------------------------

"""

import cgi
import cgitb
import hashlib
import os
import re
import shutil
import subprocess
import tempfile

from django import template
from django.conf import settings
from django.utils.encoding import force_unicode, smart_str
from django.utils.html import escape


# Allow the Django template rendering to work without a project.
settings.configure()


class Response(object):

    default_headers = {
        'Status': '200 OK',
        'Content-Type': 'text/html',
    }

    def __init__(self, content='', headers=None):
        self.content = content
        self.headers = headers or self.default_headers

    def print_content(self):
        print self.content

    def print_headers(self):
        for key, value in self.headers.iteritems():
            print '%s: %s' % (key, value)
        print

    def render(self):
        self.print_headers()
        self.print_content()


class TracebackResponse(Response):

    default_headers = {
        'Status': '500 Internal Server Error',
        'Content-Type': 'text/html',
    }

    def print_content(self):
        cgitb.enable()
        raise


class ResponseException(Exception):

    def __init__(self, content=''):
        self.response = Response(content, self.headers)

    def render(self):
        self.response.render()


class BadRequestResponse(ResponseException):

    headers = {
        'Status': '400 Bad Request',
        'Content-Type': 'text/plain',
    }


class Diff2HTML(object):

    html_template = '''
<html>
<head>
    <title>{{ title }}</title>
    <style type="text/css">
        html {
            font-family: monospace;
        }
        pre {
            margin: 0;
            padding: 0;
        }
        table {
            border: 1px solid #D7D7D7;
            border-spacing: 0;
            width: 100%;
        }

        div.changeset {
            margin: 2em 1em;
        }

        div.changeset th.collapse,
        div.changeset th.collapsed {
            text-align: center;
            cursor: pointer;
            color: grey;
            width: 3%;
        }
        div.changeset th.collapse:before {
            content: "-";
        }
        div.changeset th.collapsed:before {
            content: "+";
        }

        div.changeset tbody.collapsed {
            display: none;
        }

        div.changeset tr th {
            background: #F7F7F7;
            margin: 0;
            padding: .25em 0;
            text-align: left;
            font-size: x-large;
        }
        div.changeset tr th a {
            text-decoration: none;
        }

        div.changeset tr td {
            padding: 0 .5em;
        }
        div.changeset tr.first td,
        div.changeset tr:first-child td {
            padding-top: 0.25em;
        }
        div.changeset tr.last td,
        div.changeset tr:last-child td {
            padding-bottom: 0.25em;
        }

        div.changeset tr td.num {
            background: #F7F7F7;
            color: grey;
        }

        div.changeset tr td.content {
            border-left: 1px solid #D7D7D7;
            width: 99%;
        }
        div.changeset tbody tr:first-child td.content {
            border-top: 1px solid #D7D7D7;
        }

        div.changeset tr.plus td.content {
            background-color: #DFD;
        }
        div.changeset tr.minus td.content {
            background-color: #FDD;
        }
        div.changeset tr.skip td.content {
            background-color: #F7F7F7;
            border-top: 1px solid #D7D7D7;
            border-bottom: 1px solid #D7D7D7;
            border-left: none;
        }
        div.changeset tr.property td.content {
            background-color: #FFD;
        }
    </style>
</head>
<body>

<div class="list">
    {% if diffs %}
    <h2>
        {% if relative and working and working != "trunk" %}
            Local changes for <a href="?path=^/{{ relative }}">{{ working }}</a>:
        {% else %}
            {{ title }}:
        {% endif %}
    </h2>
    <ol>
        {% for filename, changes in diffs %}
        <li><a href="#{{ forloop.counter }}">{{ filename }}</a></li>
        {% endfor %}
    </ol>
    {% else %}
    <h2>No changes.</h2>
    {% endif %}
</div>

{% for filename, changes in diffs %}
<div class="changeset">
    <a name="{{ forloop.counter }}"></a>
    <table>
        <thead>
            <tr>
                <th colspan="2"{% if filename != "." %} class="collapse" title="Toggle visibility"{% endif %}></th>
                <th>{% if trac %}<a href="{{ trac }}{{ filename }}" target="_blank" title="View latest version on trac">{% endif %}{{ filename }}{% if trac %}</a>{% endif %}</th>
            </tr>
        </thead>
        <tbody>
            {% for line in changes %}
            <tr class="{{ line.classname }}">
                {% spaceless %}{% if line.left_line == '...' and line.right_line == '...' %}
                <td class="num" colspan="2" align="center">...</td>
                {% else %}
                <td class="num">{% if line.classname != "plus" %}{{ line.left_line|safe }}{% endif %}</td>
                <td class="num">{% if line.classname != "minus" %}{{ line.right_line|safe }}{% endif %}</td>
                {% endif %}{% endspaceless %}
                <td class="content"><pre>{{ line.content|safe }}</pre></td>
            </tr>{% endfor %}
        </tbody>
    </table>
</div>
{% endfor %}

<script type="text/javascript">
    (function() {
        var elems = document.getElementsByTagName('th')
        for (var i=0; i<elems.length; i++) {
            var elem = elems[i]
            if (elem.className == 'collapse') {
                elem.onclick = function() {

                    if (this.className == 'collapse') {
                        this.className = 'collapsed'
                    } else {
                        this.className = 'collapse'
                    }

                    var table = this.parentNode
                    while (table) {
                        if (table.tagName.match(/table/i)) {
                            break
                        }
                        table = table.parentNode
                    }
                    if (table) {
                        for (var j=0; j<table.childNodes.length; j++) {
                            var child = table.childNodes[j]
                            if (child.tagName && child.tagName.match(/tbody/i)) {
                                child.className = this.className
                                break
                            }
                        }
                    }

                }
            }
        }
    })()
</script>

</body></html>
    '''

    @staticmethod
    def parse_unified_diff(unified_diff):

        diffs = {}
        filename = None
        is_changeset = False
        left_line = 0
        right_line = 0

        for line in unified_diff.splitlines():

            if line.startswith('=='):
                continue
            if line.startswith('__'):
                continue
            if line.startswith('--'):
                continue
            if line.startswith('++'):
                continue

            file_match = re.match(r'(Index|Property changes on): (.+)', line)
            if file_match:
                is_changeset = (file_match.group(1) == 'Index')
                filename = file_match.group(2)
                diffs.setdefault(filename, [])
                continue

            line_number_match = re.match('@@ -(\d+),\d+ \+(\d+),\d+ @@', line)
            if line_number_match:

                # Get the line numbers and subtract one. This is because
                # we increment the numbers before outputting each line of
                # data, rather than incrementing afterwards.
                left_line = int(line_number_match.group(1)) - 1
                right_line = int(line_number_match.group(2)) - 1

                # If there is a previous line, then show a "skip" line.
                # Otherwise this is the first line of the diff.
                if diffs[filename]:
                    # Firstly, add the "last" class to the previous line
                    # so that it can be styled better.
                    diffs[filename][-1]['classname'] += ' last'
                    # Now, add a skip line so it will be displayed nicely.
                    diffs[filename].append({
                        'is_changeset': True,
                        'classname': 'skip',
                        'content': '&nbsp;',
                        'left_line': '...',
                        'right_line': '...',
                    })

                continue

            if line.startswith('-'):
                classname = 'minus'
                left_line += 1
            elif line.startswith('+'):
                classname = 'plus'
                right_line += 1
            else:
                classname = ''
                left_line += 1
                right_line += 1

            if is_changeset:
                if line:
                    content = escape(force_unicode(line[1:], errors='replace'))
                else:
                    continue
            else:
                classname = 'property'
                content = escape(line.strip())
                if not content:
                    continue

            # If the previous line was a "skip" line, then make the current
            # line have the "first" class so that it can be styled better.
            if diffs[filename] and diffs[filename][-1]['classname'] == 'skip':
                classname += ' first'

            # Add the line to the final output.
            diffs[filename].append({
                'classname': classname,
                'content': content,
                'left_line': is_changeset and left_line or '&nbsp;',
                'right_line': is_changeset and right_line or '&nbsp;',
            })

        return diffs

    @classmethod
    def render_parsed_diffs(cls, parsed_diffs, context_data=None):
        context = template.Context({
            'title': 'Files',
            'trac': '',
        })
        if context_data:
            context.update(context_data)
        context.update({
            'diffs': sorted(parsed_diffs.items()),
        })
        return template.Template(cls.html_template.strip()).render(context)

    @classmethod
    def convert_to_html(cls, unified_diff, context_data=None, exclude_patterns=()):
        diffs = cls.parse_unified_diff(unified_diff)

        for pattern in exclude_patterns:
            exclude = re.compile(pattern)
            for filename in diffs.keys():
                if exclude.search(filename):
                    del diffs[filename]

        html = cls.render_parsed_diffs(diffs, context_data=context_data)
        return smart_str(html)


class DiffHandler(object):

    @staticmethod
    def _get_exclude_patterns():
        """
        Get regular expressions from the query string,
        used to exclude filenames from the output.

        """
        try:
            query_string = os.environ.get('QUERY_STRING', '')
            parameters = cgi.parse_qs(query_string)
            return parameters['exclude']
        except KeyError:
            return []

    @staticmethod
    def _get_path():
        """Get the target URL from the query string."""
        try:
            query_string = os.environ.get('QUERY_STRING', '')
            parameters = cgi.parse_qs(query_string)
            path = parameters['path'][0]
            return path
        except (KeyError, IndexError):
            return ''

    @staticmethod
    def _get_svn_root(working_path):

        stdout, stderr = subprocess.Popen(
            args=['grep svn+ssh .svn/entries 2>/dev/null | head -1'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=working_path,
            shell=True,
        ).communicate()
        if stderr:
            raise BadRequestResponse(content='Error!\n%s' % stderr)
        else:
            working_url = stdout.strip()

        root_path = working_path
        root_url = working_url

        # Keep going up a directory until we're no longer in SVN.
        # The last working level is the "svn root."
        test_path = root_path
        test_url = root_url
        while os.path.exists(os.path.join(test_path, '/.svn/entries')):
            root_path = test_path
            root_url = test_url
            test_path = os.path.dirname(test_path)
            test_url = os.path.dirname(test_url)

        return {
            'path': root_path,
            'url': root_url,
        }

    @classmethod
    def _get_local_changes(cls, exclude_patterns=()):

        stdout, stderr = subprocess.Popen(
            args=('svn', 'diff'),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.environ['SVN_ROOT'],
        ).communicate()
        if stderr:
            raise BadRequestResponse(content='Error!\n%s' % stderr)

        svn_root = cls._get_svn_root(os.environ['SVN_ROOT'])
        url = svn_root['url']
        url_root = os.environ['SVN_URL_ROOT']
        relative = re.sub(r'^%s' % re.escape(url_root), '', url)
        working = os.path.basename(relative)

        context_data = {
            'title': 'Local changes for %s' % working,
            'working': working,
            'relative': relative,
            'trac': '%s%s/' % (os.environ['LINK_ROOT'], relative),
        }

        if stdout:
            html = Diff2HTML.convert_to_html(stdout, context_data=context_data, exclude_patterns=exclude_patterns)
        else:
            # Render an empty list of diffs.
            html = Diff2HTML.render_parsed_diffs({}, context_data=context_data)

        return Response(content=html)

    @classmethod
    def _get_branch_changes(cls, path, exclude_patterns=()):

        revision = cls._svn_revision(path)

        old_path = '^/trunk@%d' % revision
        new_path = '%s@%d' % (path, revision)

        cache_key = hashlib.md5()
        cache_key.update(old_path)
        cache_key.update(new_path)
        for pattern in exclude_patterns:
            cache_key.update(pattern)

        cache_path = os.path.join('/tmp', 'diff-%s.html' % cache_key.hexdigest())
        if os.path.exists(cache_path):

            html = open(cache_path).read()

        else:

            command = ('svn', 'diff', old_path, new_path)
            stdout, stderr = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
            if stderr:
                raise BadRequestResponse(content=stderr)
            if not stdout:
                raise BadRequestResponse(content='Could not get diff for %s' % new_path)

            context_data = {
                'title': 'Differences between %s and %s' % (old_path, new_path),
                'trac': '%s%s/' % (os.environ['LINK_ROOT'], path.replace('^/', '')),
            }
            html = Diff2HTML.convert_to_html(stdout, context_data=context_data, exclude_patterns=exclude_patterns)

            temp_file, temp_path = tempfile.mkstemp()
            temp_file = open(temp_path, 'w')
            temp_file.write(html)
            temp_file.close()

            shutil.move(temp_path, cache_path)

        return Response(content=html)

    @staticmethod
    def _svn_revision(path):
        command = ('svn', 'info', path)
        stdout, stderr = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
        if stderr:
            raise BadRequestResponse(content='Error!\n%s' % stderr)
        if not stdout:
            raise BadRequestResponse(content='Could not get information for "%s"' % path)
        match = re.search(r'Last Changed Rev: (\d+)', stdout)
        if not match:
            raise BadRequestResponse(content='Could not get last revision for %s\n\n%s' % (path, stdout))
        return int(match.group(1))

    @classmethod
    def get_response(cls):
        path = cls._get_path()
        exclude = cls._get_exclude_patterns()
        if path:
            return cls._get_branch_changes(path, exclude)
        else:
            return cls._get_local_changes(exclude)


if __name__ == '__main__':

    try:
        response = DiffHandler.get_response()
    except ResponseException, error:
        response = error
    except:
        response = TracebackResponse()

    response.render()
