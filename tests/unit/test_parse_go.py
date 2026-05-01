import pytest

from combfind.db import create_schema, get_connection
from combfind.pipeline.parse import run

SAMPLE = b"""\
package auth

// Server handles HTTP requests.
type Server struct {
\thost string
\tport int
}

// Handler defines the request interface.
type Handler interface {
\tHandle(req string) string
}

// NewServer creates a new Server.
func NewServer(host string, port int) *Server {
\treturn &Server{host: host, port: port}
}

// Start begins listening.
func (s *Server) Start() error {
\treturn nil
}

func (s *Server) stop() {}
"""


@pytest.fixture
def env(tmp_path):
    src = tmp_path / "pkg" / "auth"
    src.mkdir(parents=True)
    (src / "server.go").write_bytes(SAMPLE)
    db_path = str(tmp_path / "test.db")
    conn = get_connection(db_path)
    create_schema(conn)
    conn.close()
    return str(tmp_path), db_path


def _symbols(db_path):
    conn = get_connection(db_path)
    rows = conn.execute("SELECT name, kind, qualified_name, docstring FROM symbols").fetchall()
    conn.close()
    return {r["name"]: dict(r) for r in rows}


def test_struct_extracted(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    assert "Server" in syms
    assert syms["Server"]["kind"] == "struct"
    assert syms["Server"]["qualified_name"] == "auth.Server"


def test_interface_extracted(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    assert syms["Handler"]["kind"] == "interface"


def test_function_extracted(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    assert syms["NewServer"]["kind"] == "function"
    assert syms["NewServer"]["qualified_name"] == "auth.NewServer"


def test_method_extracted(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    assert syms["Start"]["kind"] == "method"
    assert syms["Start"]["qualified_name"] == "auth.Server.Start"


def test_docstring_on_function(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    assert "creates a new Server" in (syms["NewServer"]["docstring"] or "")


def test_docstring_on_type(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    assert "HTTP requests" in (syms["Server"]["docstring"] or "")
