import sys

if sys.argv[1:] == ["--workbench"]:
    from bifang.workbench import main
elif sys.argv[1:] == ["--setup"]:
    from bifang.setup_protocol import main
elif not sys.argv[1:]:
    from bifang.server import main
else:
    raise SystemExit("Unsupported sidecar arguments")

main()
