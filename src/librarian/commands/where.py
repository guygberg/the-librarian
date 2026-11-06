help = "Print the data folder for the selected Workspace"


def add_arguments(parser):
    pass


def run(args, ctx):
    print(ctx.workspace_dir)
    return 0
