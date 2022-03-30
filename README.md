## Dark Brotherhood Bot


### Objective



### Commands


### Directory
<ul>
    <li>cogs<ul>
       Contains discord.py extensions, each with a Cog that implements some of the bot's functionality
    </ul></li>
    <li>convert<ul>
        One time use files for migrating data from earlier versions
    </ul></li>
    <li>loopedfunctions<ul>
        to be run locally, it runs some function periodically
    </ul></li>
    <li>utils<ul>
        Various functions that are used throughout the bot's code
    </ul></li>
    <li>main.py<ul>
        The entry point to the bot. Run it to start the bot up!
    </ul></li>
    <li>data.db<ul>
        Stores the data (as of current version)
    </ul></li>
    <li>logs.txt<ul>
        From the start of a logging project that never took off. Does not do anything as of now.
    </ul></li>
</ul>

### Formatting

- In general, we follow [PEP 8](https://www.python.org/dev/peps/pep-0008/), [PEP 257](https://www.python.org/dev/peps/pep-0257/), & [PEP 484](https://www.python.org/dev/peps/pep-0484/) guidelines, with some exceptions

- <details>
    <summary>PEP 8 -- Style Guide for Python Code</summary>
    <ul>
        <li><a href='https://www.python.org/dev/peps/pep-0008/#indentation'>Indentation:</a> 4 spaces per indentation level</li>
        <li><a href='https://www.python.org/dev/peps/pep-0008/#tabs-or-spaces'>Indentation Method:</a> Prefer spaces</li>
        <li><a href='https://www.python.org/dev/peps/pep-0008/#maximum-line-length'>Maximum Line Length:</a> Haven't decided</li>
        <li><a href='https://www.python.org/dev/peps/pep-0008/#should-a-line-break-before-or-after-a-binary-operator'>Line Breaks with Binary Operators:</a> Break before binary</li>
        <li><a href='https://www.python.org/dev/peps/pep-0008/#blank-lines'>Blank lines (Adapted):</a><ul>
            <li>Separate imports, alongside top-level function and class definitions with three blank lines</li>
            <li>Separate method definitions inside a class are separated by two blank lines</li>
            <li>Use blank lines in functions and class methods, sparingly, to indicate logical sections</li>
        </ul></li>
        <li><a href='https://www.python.org/dev/peps/pep-0008/#source-file-encoding'> Source File Encoding:</a> UTF-8</li>
        <li><a href='https://www.python.org/dev/peps/pep-0008/#imports'>Imports (Adapted):</a><ul>
            <li>Imports are always put at the top of the file, just after any module comments and docstrings, and before module globals and constants</li>
            <li>Imports should be grouped in the following order:</li>
                <blockquote>
                    1. Module level dunder imports<br>
                    2. Standard library and <a href='https://packaging.python.org/glossary/#term-Distribution-Package'>package</a> imports<br>
                    3. Discord.py related imports<br>
                    4. Local application/library specific imports
                </blockquote>
            <li>Prefer <a href='https://realpython.com/absolute-vs-relative-python-imports/#absolute-imports'>absolute imports</a> over <a href='https://realpython.com/absolute-vs-relative-python-imports/#relative-imports'>relative imports</a></li>
            <li>Avoid wildcard imports (i.e. <code>from module import *</code>)</li>
        </ul></li>
        <li><a href='https://www.python.org/dev/peps/pep-0008/#module-level-dunder-names'>Module Level Dunder Names:</a> Should be placed after the module docstring but before any import statements <em>except</em> <code>from __future__</code> imports</li>
        <li><a href='https://www.python.org/dev/peps/pep-0008/#string-quotes'>String Quotes:</a> Use single quotes</li>
        <li><a href='https://www.python.org/dev/peps/pep-0008/#whitespace-in-expressions-and-statements'>Whitespace in Expressions and Statements</a></li>
        <li><a href='https://www.python.org/dev/peps/pep-0008/#when-to-use-trailing-commas'>When to Use Trailing Commas:</a> Use when making a tuple of one element, or when a list of values, arguments or imported items is expected to be extended over time</li>
        <li><a href='https://www.python.org/dev/peps/pep-0008/#comments'>Comments:</a> Keep them up-to-date, in complete sentences, easily understandable, and in English<ul>
            <li><a href='https://www.python.org/dev/peps/pep-0008/#block-comments'>Block Comments:</a> Starts with <code>#</code> and a single space, seperate paragraphs inside a block comment with a line containing a single <code>#</code></li>
            <li><a href='https://www.python.org/dev/peps/pep-0008/#inline-comments'>Inline Comments:</a> Use sparingly</li>
            <li><a href='https://www.python.org/dev/peps/pep-0008/#documentation-strings'>Documentation Strings:</a> Refer to <a href='https://www.python.org/dev/peps/pep-0257/'>PEP 257</a></li>
        </ul></li>
        <li><a href='https://www.python.org/dev/peps/pep-0008/#naming-conventions'>Naming Conventions (Adapted):</a><ul>
            <li><a href='https://www.python.org/dev/peps/pep-0008/#descriptive-naming-styles'>Naming Styles:</a><ul>
                <li><a href='https://www.python.org/dev/peps/pep-0008/#function-and-variable-names'>Functions, Variables</a> and <a href='https://www.python.org/dev/peps/pep-0008/#method-names-and-instance-variables'>Class Methods</a>: <code>lowercase</code> or <code>lower_case_with_underscores</code></li>
                <li><a href='python.org/dev/peps/pep-0008/#class-names'>Classes</a>: <code>CapitalizedWords</code></li>
                <li><a href='https://www.python.org/dev/peps/pep-0008/#module-level-dunder-names'>Module Level Dunders</a>: <code>__double_leading_and_trailing_underscore__</code></li>
            </ul></li>
            <li><a href='https://www.python.org/dev/peps/pep-0008/#names-to-avoid'>Names to Avoid:</a> Don't use 'l', 'O', or 'I' as single character variable names</li>
            <li><a href='https://www.python.org/dev/peps/pep-0008/#package-and-module-names'>Package and Module Names:</a> Should have short, all-lowercase names, with underscores if it improves readability</li>
            <li><a href='https://www.python.org/dev/peps/pep-0008/#function-and-method-arguments'>Function and Method Arguments:</a><ul>
                <li>Always use <code>self</code> for the first argument to instance methods</li>
                <li>Always use <code>cls</code> for the first argument to class methods.</li>
            </ul></li>
            <li><a href='https://www.python.org/dev/peps/pep-0008/#designing-for-inheritance'>Designing for Inheritance:</a> Only needed class methods and instance variables (collectively 'attributes') should be public (If in doubt, choose non-public, can change later on if needed)</li>
            <li><a href='https://www.python.org/dev/peps/pep-0008/#public-and-internal-interfaces'>Public and Internal Interfaces:</a> Explicitly declare the names of public attributes in the public API using the <code>__all__</code> attribute</li>
        </ul></li>
        <li><a href='https://www.python.org/dev/peps/pep-0008/#programming-recommendations'>Programming Recommendations</a><ul>
            <li><a href='https://www.python.org/dev/peps/pep-0008/#function-annotations'>Function Annotations</a></li>
            <li><a href='https://www.python.org/dev/peps/pep-0008/#variable-annotations'>Variable Annotations</a></li>
        </ul></li>
    </ul></details>

- <details open>
    <summary>PEP 257 -- Docstring Conventions</summary>
    <ul>
        <li><a href=''></a></li>
        <li><a href=''></a></li>
        <li><a href=''></a></li>
        <li><a href=''></a></li>
        <li><a href=''></a></li>
    </ul></details>

- <details open>
    <summary>PEP 484 -- Type Hints</summary>
    <ul>
        <li><a href=''></a></li>
        <li><a href=''></a></li>
        <li><a href=''></a></li>
        <li><a href=''></a></li>
        <li><a href=''></a></li>
    </ul></details>


### Migration of data
To migrate data from earlier versions, use the convert directory. Instructions can be found in instructions.txt there.


### Links to relevant resources

- P&W API v3 (GraphQL)
    - [GraphQL Basics](https://graphql.org/learn/queries/)
    - [GraphQL Playground](https://api.politicsandwar.com/graphql-playground)

- discord.py
    - [Official Releases](https://pypi.org/project/discord.py/)
    - [Development Version](https://github.com/Rapptz/discord.py)
    - [discord.ui examples](https://github.com/Rapptz/discord.py/tree/45d498c1b76deaf3b394d17ccf56112fa691d160/examples/views)

- repl.it
    - [Configure repl.it Run Button](https://docs.replit.com/programming-ide/configuring-run-button)
    - [Store Keys / Tokens Privately](https://docs.replit.com/programming-ide/storing-sensitive-information-environment-variables)