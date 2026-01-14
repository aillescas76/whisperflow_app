# **Pythonic Design & General Programming Best Practices**

This document serves as the unified standard for code quality, architectural design, and stylistic consistency. It combines the specific nuances of the Python language with universal software engineering principles.

## **1\. Python Stylistic Standards (PEP 8\)**

Consistency is the primary goal of PEP 8\. When the code looks consistent, it becomes easier to read and maintain.

### **Naming Conventions**

* **Functions & Variables:** Use snake\_case (e.g., calculate\_total\_price).  
* **Classes:** Use PascalCase (e.g., UserAccountManager).  
* **Constants:** Use SCREAMING\_SNAKE\_CASE (e.g., MAX\_RETRIES \= 5).  
* **Private Members:** Use a leading underscore for internal-only attributes (e.g., \_internal\_state).

### **Layout & Formatting**

* **Indentation:** 4 spaces per level. **Never** use tabs.  
* **Line Length:** Limit lines to 110 characters. Use parentheses for long expressions rather than backslashes.  
* **Imports:** Group imports in this order:  
  1. Standard library  
  2. Related third-party  
  3. Local application/library specific  
* **Whitespace:** \* Two blank lines before top-level classes and functions.  
  * One blank line before class methods.  
  * Avoid extraneous whitespace inside parentheses or immediately before commas.

## **2\. Pythonic Idioms (Writing "Good" Python)**

Python provides unique features that, when used correctly, make code more expressive.

### **Explicit is Better than Implicit**

Always prefer clear, readable logic over "clever" one-liners.

* **Bad:** if not x \== None:  
* **Good:** if x is not None:

### **Truth Value Testing**

Use the fact that empty sequences (lists, strings, dicts) evaluate to False.

* **Preferred:** if not my\_list: (instead of if len(my\_list) \== 0:)

### **Context Managers (with)**

Always use with for resource management (files, sockets, database connections) to ensure they are properly closed even if an error occurs.

### **Type Hinting**

Use type hints to make code self-documenting and to enable better IDE support/linting.

def fetch\_user\_data(user\_id: int) \-\> dict\[str, str\]:  
    ...

## **3\. Universal Design Principles (SOLID)**

Apply these to ensure your object-oriented designs are flexible and robust.

1. **Single Responsibility (SRP):** A class should do one thing. If a class handles database logic *and* UI formatting, split it.  
2. **Open/Closed (OCP):** You should be able to add new functionality (extend) without changing existing code (modify).  
3. **Liskov Substitution (LSP):** Subclasses must be usable in place of their parent classes without breaking the app.  
4. **Interface Segregation (ISP):** Don't force a class to implement methods it doesn't use. Split large interfaces into smaller, specific ones.  
5. **Dependency Inversion (DIP):** Depend on abstractions (interfaces/abstract classes), not concrete implementations.

## **4\. Fundamental "Clean Code" Rules**

### **DRY (Don't Repeat Yourself)**

Every piece of logic should have a single representation. If you are copy-pasting code, you should probably be creating a function or a shared module.

### **KISS (Keep It Simple, Stupid)**

Avoid over-engineering. Do not build a complex "Framework" for a problem that can be solved with three functions. Readability is the most important feature of any code.

### **YAGNI (You Ain't Gonna Need It)**

Do not implement features or "hooks" for future requirements that don't exist yet. Code for the requirements you have today.

### **Composition Over Inheritance**

Inheritance creates a "strong" link between classes that is hard to break. Composition (having an instance of another class as an attribute) is much more flexible and easier to test.

## **5\. Error Handling & Defensive Programming**

### **Fail Fast**

Validate your data early. If a function receives a null when it expects an int, raise a ValueError immediately rather than letting the error propagate into deep logic.

### **Specific Exceptions**

Never use a "bare" except:. Always catch the specific exception you expect (e.g., FileNotFoundError, KeyError).

### **EAFP vs. LBYL**

Python encourages **EAFP** (Easier to Ask for Forgiveness than Permission).

* **LBYL (Look Before You Leap):** if file\_exists: open(file)  
* **EAFP (Pythonic):** try: open(file) except FileNotFoundError: ...

## **6\. Documentation & Tooling**

### **Docstrings**

All public modules, functions, classes, and methods should have a docstring using """Triple Quotes""". Explain the *purpose* and the *arguments*, not just a restate the name.

### **Tooling Recommendations**

To enforce these rules automatically, include these in your workflow:

* **Linter:** Ruff or Flake8 (for style and logic errors).  
* **Formatter:** Black (for "uncompromising" formatting).  
* **Type Checker:** Mypy (to verify type hints).  
* **Testing:** Pytest (for unit and integration tests).

## **7\. The Boy Scout Rule**

"Leave the code better than you found it." If you touch a file to fix a bug, take 30 seconds to clean up a poorly named variable or a missing comment in that same file.
