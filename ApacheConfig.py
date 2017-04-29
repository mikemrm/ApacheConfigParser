import re, shlex
if not hasattr(shlex, 'quote'):
	if not hasattr(re, 'ASCII'):
		setattr(re, 'ASCII', 256)
	_find_unsafe = re.compile(r'[^\w@%+=:,./-]', re.ASCII).search

	def quote(s):
		"""Return a shell-escaped version of the string *s*."""
		if not s:
			return "''"
		if _find_unsafe(s) is None:
			return s

		# use single quotes, and put single quotes into double quotes
		# the string $'b is then quoted as '$'"'"'b'
		return "'" + s.replace("'", "'\"'\"'") + "'"
	setattr(shlex, 'quote', quote)

APACHE_ROOT = 'APACHE_SECTION_ROOT'

match_comment = re.compile(br'^\s*#\s*(.*)$')
match_statement = re.compile(br'^\s*[^\s<]+\s*.*$')
match_section_start = re.compile(br'^\s*<([^\s]+)(\s+)(.*)>$')
match_section_end = re.compile(br'^\s*<\/([^\s]+).*>$')
match_line_endings = re.compile(br"\r?\n")

class ApacheParseException(Exception): pass

class ApacheItemList(list):

	def insertBefore(self, n, o):
		for j in range(len(self)):
			if self[j] is o:
				self.insert(j, n)
				return self

	def find(self, name, *arguments):
		for i in self:
			i_class = i.__class__
			if i.matches(name, *arguments):
				return i

	def findAll(self, name, *arguments):
		found = self.__class__()
		for i in self:
			if i.matches(name, *arguments):
				found.append(i)
		return found

	def findChild(self, name, *arguments):
		for i in self:
			i_class = i.__class__
			if i_class in [ApacheSection, ApacheRoot]:
				return i.children.find(name, *arguments)

	def findChildren(self, name, *arguments):
		found = self.__class__()
		for i in self:
			i_class = i.__class__
			if i_class in [ApacheSection, ApacheRoot]:
				found += i.children.findAll(name, *arguments)
		return found

	def update(self, *values, **kwargs):
		replace_all = kwargs.pop('replace_all', False)
		for i in self:
			i.update(*values, replace_all = replace_all)
		return self

class ApacheItem(object):
	def __init__(self, line, parent, file, index):
		self.line = line
		self.parent = parent
		self.file = file
		self.index = index

	def matches(self, name, *arguments):
		return None

	def update(self, *values, **kwargs):
		replace_all = kwargs.pop('replace_all', False)
		return self

	def __str__(self):
		return self.line

	def __repr__(self):
		return '<%s @ Line %d>' % (self.__class__.__name__, self.index)

class ApacheEmptyLine(object):
	def __init__(self, index):
		self.index = index

	def matches(self, name, *arguments):
		return None

	def update(self, *values, **kwargs):
		replace_all = kwargs.pop('replace_all', False)
		return self

	def __str__(self):
		return ''

	def __repr__(self):
		return '<%s>' % (self.__class__.__name__,)

class ApacheComment(ApacheItem):
	def __init__(self, line, parent, file, index):
		super(self.__class__, self).__init__(line, parent, file, index)
		self.comment = None
		self.parse()

	def parse(self):
		parts = re.search(match_comment, self.line)
		if not parts:
			raise ApacheParseException('Failed to parse %s at line %d' % (self.file, self.index))
		self.comment = parts.group(1)

	def matches(self, name, *arguments):
		if self.comment.lower() == name.lower():
			return True

	def update(self, *values, **kwargs):
		replace_all = kwargs.pop('replace_all', False)
		self.comment = ' '.join(values)
		return self

	def __str__(self):
		return '# ' + self.comment.decode('utf-8')

class ApacheStatement(ApacheItem):
	def __init__(self, line, parent, file, index):
		super(self.__class__, self).__init__(line, parent, file, index)
		self.module = None
		self.arguments = []
		self.parse()

	def parse(self):
		parts = shlex.split(self.line.decode('utf-8'))
		if not parts:
			raise ApacheParseException('Failed to parse %s at line %d' % (self.file, self.index))
		self.module = parts[0]
		self.arguments = parts[1:]

	def matches(self, name, *arguments):
		if self.module.lower() == name.lower() and self.arguments[:len(arguments)] == list(arguments):
			return True

	def update(self, *values, **kwargs):
		replace_all = kwargs.pop('replace_all', False)
		self.arguments = values if replace_all else (list(values) + self.arguments[len(values):])
		return self

	def __str__(self):
		quoted_args = [shlex.quote(x) for x in self.arguments]
		return '%s %s' % (self.module, ' '.join(quoted_args))

	def __repr__(self):
		return "<%s '%s' @ Line %d>" % (self.__class__.__name__, self.module, self.index)

class ApacheSection(ApacheItem):
	def __init__(self, line, parent, file, index):
		super(ApacheSection, self).__init__(line, parent, file, index)
		self.name = None
		self.arguments = None
		self.children = ApacheItemList()
		self.parse()

	def parse(self):
		if self.line:
			parts = re.search(match_section_start, self.line)
			if not parts:
				raise ApacheParseException('Failed to parse %s at line %d' % (self.file, self.index))
			self.name = parts.group(1).decode('utf-8')
			if parts.group(3):
				self.arguments = shlex.split(parts.group(3).decode('utf-8'))

	def matches(self, name, *arguments):
		if self.name.lower() == name.lower() and self.arguments[:len(arguments)] == list(arguments):
			return True

	def update(self, *values, **kwargs):
		replace_all = kwargs.pop('replace_all', False)
		self.arguments = values if replace_all else (list(values) + self.arguments[len(values):])
		return self

	def find(self, name, *arguments):
		return self.children.find(name, *arguments)

	def findAll(self, name, *arguments):
		return self.children.findAll(name, *arguments)

	def appendChild(self, i):
		self.children.append(i)

	def insertBefore(self, n, o):
		self.children.insertBefore(n, o)

	def renderEndOfSection(self):
		return '</%s>' % (self.name,)

	def __str__(self):
		quoted_args = [shlex.quote(x) for x in self.arguments]
		return '<%s %s>' % (self.name, ' '.join(quoted_args))

	def __repr__(self):
		return "<%s '%s' @ Line %d>" % (self.__class__.__name__, self.name, self.index)

class ApacheRoot(ApacheSection):
	def __repr__(self):
		return "<%s>" % (self.__class__.__name__,)

class ApacheParser:
	def __init__(self, file, indent=4):
		self.file = file
		self.index = 0
		self.indent_size = indent
		self.root = ApacheRoot(None, None, self.file, self.index)
		self.path = [self.root]
		self.parse()

	def parseLine(self, line):
		if re.match(match_comment, line):
			return ApacheComment(line, self.path[-1], self.file, self.index)
		elif re.match(match_statement, line):
			return ApacheStatement(line, self.path[-1], self.file, self.index)
		elif re.match(match_section_start, line):
			return ApacheSection(line, self.path[-1], self.file, self.index)
		elif re.match(match_section_end, line):
			return None
		elif not line.strip():
			return ApacheEmptyLine(self.index)
		else:
			raise ApacheParseException('Failed to parse %s at line %d' % (self.file, self.index))

	def parseFile(self):
		line = self.file.readline()
		while line:
			self.index += 1
			parsed = self.parseLine(line)
			if parsed == None:
				self.path.pop()
			else:
				self.path[-1].appendChild(parsed)
				if parsed.__class__ == ApacheSection:
					self.path.append(parsed)
			line = self.file.readline()
		return self.root

	def find(self, name, *arguments):
		return self.root.find(name, *arguments)

	def findAll(self, name, *arguments):
		return self.root.findAll(name, *arguments)

	def parse(self):
		return self.parseFile()

	def renderIndent(self, indent):
		return (' ' * self.indent_size) * indent

	def renderLines(self, item, indent = 0):
		item_class = item.__class__
		isRoot = item_class == ApacheRoot
		output_lines = []
		if isRoot or item_class == ApacheSection:
			if not isRoot:
				output_lines.append(self.renderIndent(indent) + str(item))
			else:
				indent -= 1
			for child in item.children:
				output_lines += self.renderLines(child, indent + 1)
			if not isRoot:
				output_lines.append(self.renderIndent(indent) + item.renderEndOfSection())
		elif item.__class__ in [ApacheStatement, ApacheComment, ApacheEmptyLine]:
			output_lines.append(self.renderIndent(indent) + str(item))
		return output_lines

	def render(self, item = None):
		item = self.root if not item else item
		return bytes("\n".join(self.renderLines(item)), 'UTF-8')

if __name__ == '__main__':
	import sys
	if len(sys.argv) > 2 and len(sys.argv) <= 5:
		input_file = open(sys.argv[1], 'rb')
		parsed = ApacheParser(input_file)
		input_file.close()
		search_items = sys.argv[2].split('.')
		last_item_name = search_items[-1]
		current_value = sys.argv[3] if len(sys.argv) >= 4 else None
		new_value = sys.argv[4] if len(sys.argv) == 5 else None
		last_items = parsed.findAll(search_items[0])
		del search_items[0]
		for item in search_items:
			last_items = last_items.findChildren(item)
		if current_value:
			last_items = last_items.findAll(last_item_name, *shlex.split(current_value))
		if last_items:
			for item in last_items:
				render_item = item
				if new_value != None:
					item.update(*shlex.split(new_value), replace_all = True)
					render_item = item.parent
				print(parsed.render(render_item).decode('utf-8'))
		else:
			print('Failed to find any items')
			sys.exit(1)
	else:
		print(sys.argv[0] + ' FILE VARIABLE1.VARIABLE2 [CURRENT_VALUE [NEW_VALUE]]')
		sys.exit(1)