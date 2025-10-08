import PyInstaller.__main__
import os
import shutil

def build_app():
    print("Starting application build...")

    # Define paths
    project_root = os.path.abspath(os.path.dirname(__file__))
    main_script = os.path.join(project_root, 'src', 'main.py')
    env_file = os.path.join(project_root, '.env')
    resource_dir = os.path.join(project_root, 'Resource')
    dist_dir = os.path.join(project_root, 'dist')
    build_dir = os.path.join(project_root, 'build')

    # Clean up previous builds
    if os.path.exists(dist_dir):
        shutil.rmtree(dist_dir)
        print(f"Cleaned up existing 'dist' directory: {dist_dir}")
    if os.path.exists(build_dir):
        shutil.rmtree(build_dir)
        print(f"Cleaned up existing 'build' directory: {build_dir}")

    # PyInstaller options
    # --noconfirm: Overwrite previous builds without asking
    # --onefile: Create a single executable file
    # --name: Name of the executable
    # --add-data: Add non-code files or directories
    #   Format: 'source;destination' (Windows) or 'source:destination' (Unix/macOS)
    pyinstaller_args = [
        main_script,
        '--noconfirm',
        '--onefile',
        '--name=GameTextTranslator',
        f'--add-data={env_file}{os.pathsep}.',
        f'--add-data={resource_dir}{os.pathsep}Resource',
        '--distpath', dist_dir,
        '--workpath', build_dir,
    ]

    print(f"Running PyInstaller with arguments: {pyinstaller_args}")
    PyInstaller.__main__.run(pyinstaller_args)

    print("Build process finished.")
    print(f"Executable can be found in: {dist_dir}")

if __name__ == '__main__':
    build_app()
