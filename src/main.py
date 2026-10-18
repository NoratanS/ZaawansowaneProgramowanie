"""Run from the src directory.

    cd src
    python main.py              # entry point
    python -m magazine.Order    # a module inside the package

Running `python magazine/Order.py` directly fails with
`ModuleNotFoundError: No module named 'magazine'`, because Python adds the
script's own directory (magazine/) to sys.path, not src/.
"""

from magazine import Product

pen = Product.Product("Pen", 2.5)
notebook = Product.Product("Notebook", 12)

print(pen)
print(notebook)
