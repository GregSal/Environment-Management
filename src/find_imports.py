# -*- coding: utf-8 -*-
"""
Created on Mon Jul 12 13:21:33 2021

@author: Greg Salomons

Identifies package dependencies for a given project or solution.
"""


#%% Imports
from pathlib import Path
from pprint import pprint
import re
import xml.etree.ElementTree as ET

import pandas as pd
import xlwings as xw


#%% Get Requirements
def get_requirements(root_path: Path)->pd.DataFrame:
    requirements_files = [file for file in root_path.glob('requirements.txt')]
    if requirements_files:
        req_list = list()
        for requirements_file in requirements_files:
            project_name = requirements_file.parent.name
            for line in requirements_file.read_text().splitlines():
                token = line.index('==')
                package = line[:token]
                version = line[token+2:]
                pkg = {
                    'Project': project_name,
                    'Package': package,
                    'Version': version
                    }
                req_list.append(pkg)
        req_df = pd.DataFrame(req_list)
        req_df.set_index(['Project', 'Package'], inplace=True)
    else:
        req_df = pd.DataFrame()
    return req_df


#%% Find Projects in solution
def get_solution(root_path)->pd.DataFrame:
    solution_files = [file for file in root_path.glob('*.sln')]
    if solution_files:
        solution_file = solution_files[0]
        sln_txt = solution_file.read_text().splitlines()
        proj_lines = [line for line in sln_txt if line.startswith('Project')]
        proj_list = list()
        for line in proj_lines:
            name_start = line.index(' = "') + 4
            name_end = line.index('", "', name_start)
            name = line[name_start:name_end]
            path_start = name_end + 4
            path_end = line.index('", "', path_start)
            proj_path = line[path_start:path_end]
            proj_ref = {
                'Name': name,
                'Folder': proj_path
                }
            proj_list.append(proj_ref)
        sln_df = pd.DataFrame(proj_list)
        sln_df.set_index('Name', inplace=True)
        solution_exists = True
    else:
        sln_df = pd.DataFrame()
        solution_exists = False
    return sln_df


#%% Find Project Files
def get_projects(root_path: Path)->pd.DataFrame:
    ns = {'msp': r'http://schemas.microsoft.com/developer/msbuild/2003'}
    project_files = [file.name for file in root_path.glob('**/*.pyproj')]
    project_info = list()
    for proj in root_path.glob('**/*.pyproj'):
        tree = ET.parse(proj)
        root = tree.getroot()
        project = root.find(r'msp:PropertyGroup/msp:Name', namespaces=ns)
        if project is not None:
            project_name = project.text
        else:
            project_name = proj.parent.name
        project_folder = str(proj.parent)
        for included in root.findall(r'msp:ItemGroup/msp:Compile', namespaces=ns):
            project_file = {
                'Folder': project_folder,
                'Name': project_name,
                'File': included.get('Include')
                }
            project_info.append(project_file)
    if len(project_info) > 0:
        project_df = pd.DataFrame(project_info)
        project_df.set_index('Name', inplace=True)
    else:
        project_df = pd.DataFrame()
    return project_df


#%% Get imports
def get_imports(root_path: Path)->pd.DataFrame:
    # Patterns for identifying import statements in python files.
    pattern1 = re.compile('from[ ]+([^ \t]+)[ ]+import[ ]+([^\n]+)')
    pattern2 = re.compile('import[ ]+([^ \t]+)')
    # Sort order and index for resulting DataFrame
    sort_order = ['Local Import', 'Import Module', 'Folder', 'File']
    data_index = ['Folder', 'File', 'Import Module']
    # search all python files for import statements
    python_files = root_path.glob('**/*.py')
    local_modules = list()
    import_list = list()
    for file in python_files:
        local_modules.append(file.stem)
        for line in file.read_text().splitlines():
            if 'import' in line:
                if '*' not in line:
                    found = pattern1.search(line)
                    if found:
                        import_data = {
                            'Folder': str(file.parent),
                            'File': file.name,
                            'Import Module': found.groups()[0],
                            'Import Functions': found.groups()[1]
                            }
                        import_list.append(import_data)
                    else:
                        found = pattern2.search(line)
                        if found:
                            import_data = {
                                'Folder': str(file.parent),
                                'File': file.name,
                                'Import Module': found.groups()[0]
                                }
                            import_list.append(import_data)

    if len(import_list) > 0:
        import_df = pd.DataFrame(import_list)
        import_df['Import Module'] = import_df['Import Module'].str.strip()
        # identify import statements that refer to local python files
        local_modules = set(local_modules)
        local_import = import_df['Import Module'].isin(local_modules)
        import_df.loc[local_import, 'Local Import'] = True
        import_df.loc[~local_import, 'Local Import'] = False
        # Format the DataFrame
        import_df.sort_values(sort_order, inplace=True)
        import_df.set_index(data_index, inplace=True)
        # Generate a frequency count for imports
        import_freq = import_df.groupby('Import Module').count()
    else:
        import_df = pd.DataFrame()
        import_freq = pd.DataFrame()
    return import_df, import_freq


#%% Save Data
def save_import_data(req_df, sln_df, project_df, import_df, import_freq,
                     save_file):
    with pd.ExcelWriter(save_file) as writer:
        if req_df.size > 0:
            req_df.to_excel(writer, sheet_name="Requirements")
        if sln_df.size > 0:
            sln_df.to_excel(writer, sheet_name="Solution")
        if project_df.size > 0:
            project_df.to_excel(writer, sheet_name="Projects")
        if import_df.size > 0:
            import_df.to_excel(writer, sheet_name="Imports")
            xw.view(import_df)
        if import_freq.size > 0:
            import_freq.to_excel(writer, sheet_name="Import Counts")


#%% Main
def main():
    root_path = Path.cwd() / '..'
    root_path = root_path.resolve()
    save_file = root_path / 'Environment' / "plan_check_env_analysis.xlsx"

    sln_df = get_solution(root_path)
    req_df = get_requirements(root_path)
    project_df = get_projects(root_path)
    import_df, import_freq = get_imports(root_path)

    env_packages = list(req_df.reset_index()['Package'])
    modules = import_df.reset_index()[['Import Module', 'Local Import']]
    required_pkgs = set(modules.loc[modules['Import Module'].isin(env_packages), 'Import Module'])
    print(required_pkgs)

    save_import_data(req_df, sln_df, project_df, import_df, import_freq, save_file)

if __name__ == '__Main__':
    main()
