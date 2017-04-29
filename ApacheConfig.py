import re, shlex


APACHE_ROOT = 'APACHE_SECTION_ROOT'

match_comment = re.compile(br'^\s*#\s*(.*)$')
match_statement = re.compile(br'^\s*[^\s<]+\s*.*$')
match_section_start = re.compile(br'^\s*<([^\s]+)(\s+)(.*)>$')
match_section_end = re.compile(br'^\s*<\/([^\s]+).*>$')
match_line_endings = re.compile(br"\r?\n")

class ApacheParseException(Exception): pass

class ApacheItem(object):
	def __init__(self, line, parent, file, index):
		self.line = line
		self.parent = parent
		self.file = file
		self.index = index

	def __str__(self):
		return self.line

	def __repr__(self):
		return '<%s @ Line %d>' % (self.__class__.__name__, self.index)

class ApacheEmptyLine(object):
	def __init__(self, index):
		self.index = index

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
		self.children = []
		self.parse()

	def parse(self):
		if self.line:
			parts = re.search(match_section_start, self.line)
			if not parts:
				raise ApacheParseException('Failed to parse %s at line %d' % (self.file, self.index))
			self.name = parts.group(1).decode('utf-8')
			if parts.group(3):
				self.arguments = shlex.split(parts.group(3).decode('utf-8'))

	def getChild(self, name):
		for child in self.children:
			if child.name.lower() == name.lower():
				return child

	def getAllChildren(self, name = None):
		if not name:
			return self.children
		children = []
		for child in self.children:
			if child.name.lower() == name.lower():
				children.append(child)
		return children

	def newChild(self, i):
		self.children.append(i)

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
				self.path[-1].newChild(parsed)
				if parsed.__class__ == ApacheSection:
					self.path.append(parsed)
			line = self.file.readline()
		return self.root

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

	def render(self):
		return "\n".join(self.renderLines(self.root))