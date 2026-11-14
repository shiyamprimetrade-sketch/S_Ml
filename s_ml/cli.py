"""Explicit local commands; no embedded credentials or automatic publication."""
import argparse
import json
from pathlib import Path
from .storage import Store
from .training import benchmark
from .recommendations import recommend


def main(argv=None):
    p = argparse.ArgumentParser(prog='s-ml')
    p.add_argument('--database', default='runtime/s_ml.sqlite3')
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('import-metricool').add_argument('file', type=Path)
    sub.add_parser('status')
    sub.add_parser('recommend')
    sub.add_parser('benchmark').add_argument('--output', default='runtime/benchmark')
    sub.add_parser('export').add_argument('file', type=Path)
    sub.add_parser('backup').add_argument('file', type=Path)
    delete = sub.add_parser('delete-account')
    delete.add_argument('id', type=int)
    delete.add_argument('--confirm', action='store_true', required=True)
    exp = sub.add_parser('experiment')
    exp.add_argument('--account-id', type=int, required=True)
    exp.add_argument('--hypothesis', required=True)
    exp.add_argument('--variable', required=True)
    exp.add_argument('--metric', choices=['views', 'likes', 'completion_rate'], required=True)
    exp.add_argument('--hours', type=float, default=24)
    sub.add_parser('serve').add_argument('--port', type=int, default=8766)
    args = p.parse_args(argv)
    if args.command == 'benchmark':
        result = benchmark(args.output)
    elif args.command == 'serve':
        from .server import create_server
        server = create_server(args.database, args.port)
        print(f'S_ML dashboard: http://127.0.0.1:{server.server_port}')
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return
    else:
        with Store(args.database) as store:
            if args.command == 'import-metricool':
                result = store.ingest(json.loads(args.file.read_text(encoding='utf-8')))
            elif args.command == 'status':
                result = store.summary()
            elif args.command == 'recommend':
                result = recommend(store.summary())
            elif args.command == 'export':
                args.file.parent.mkdir(parents=True, exist_ok=True)
                args.file.write_text(json.dumps(store.export(), indent=2), encoding='utf-8')
                result = {'exported': str(args.file), 'privacy': 'Private data: protect this file'}
            elif args.command == 'backup':
                store.backup(args.file)
                result = {'backup': str(args.file)}
            elif args.command == 'delete-account':
                store.delete_account(args.id)
                result = {'deleted_account': args.id, 'limitation': 'Independent backups and exports require separate deletion'}
            else:
                result = {'experiment_id': store.experiment(args.account_id, args.hypothesis, args.variable, args.metric, args.hours)}
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
