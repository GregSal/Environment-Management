# -*- coding: utf-8 -*-
'''
Test path and other package environment settings

Created on Thu Mar  3 07:54:12 2022

@author: smoke
'''


from pathlib import Path
import sys

print(f'In module: {__name__}')
print(f'current path is: {Path.cwd()}\n')

print('PythonPaths:')
for path_str in sys.path:
    print(f'\t{path_str}')

# %% Exiting module
print(f'\nDone module: {__name__}\n\n')
