import os
import tempfile
from pathlib import Path
from subprocess import Popen
from sys import stderr
from zipfile import ZipFile

import wget


class MyOpenIE:
    def __init__(self, core_nlp_version: str = "4.1.0", install_dir_path: str = None):
        if install_dir_path is None:
            self.install_dir = Path("~/.stanfordnlp_resources/").expanduser()
        else:
            self.install_dir = Path(install_dir_path)
        self.install_dir.mkdir(exist_ok=True)
        if len([d for d in self.install_dir.glob("*") if d.is_dir()]) == 0:
            # No coreNLP directories. Let's check for ZIP archives as well.
            zip_files = [d for d in self.install_dir.glob("*") if d.suffix == ".zip"]
            if len(zip_files) == 0:
                # No dir and no ZIP. Let's download it with the desired core_nlp_version.
                remote_url = (
                    "https://nlp.stanford.edu/software/stanford-corenlp-{}.zip".format(
                        core_nlp_version
                    )
                )
                print("Downloading from %s." % remote_url)
                output_filename = wget.download(remote_url, out=str(self.install_dir))
                print("\nExtracting to %s." % self.install_dir)
            else:
                output_filename = zip_files[0]
            print("Unzip %s." % output_filename)
            zf = ZipFile(output_filename)
            zf.extractall(path=self.install_dir)
            zf.close()
        target_dir = [d for d in self.install_dir.glob("*") if d.is_dir()][0]

        os.environ["CORENLP_HOME"] = str(self.install_dir / target_dir)
        from stanfordnlp.server import CoreNLPClient

        self.client = CoreNLPClient(annotators=["openie"], memory="8G")

    def annotate(
        self,
        text: str,
        annotators=["openie"],
        properties_key: str = None,
        properties: dict = None,
        simple_format: bool = True,
    ):
        """
        :param (str | unicode) text: raw text for the CoreNLPServer to parse
        :param (str) properties_key: key into properties cache for the client
        :param (dict) properties: additional request properties (written on top of defaults)
        :param (bool) simple_format: whether to return the full format of CoreNLP or a simple dict.
        :return: Depending on simple_format: full or simpler format of triples <subject, relation, object>.
        """
        # https://stanfordnlp.github.io/CoreNLP/openie.html
        core_nlp_output = self.client.annotate(
            text=text,
            annotators=annotators,
            output_format="json",
            properties_key=properties_key,
            properties=properties,
        )
        if simple_format:
            triples = []
            for sentence in core_nlp_output["sentences"]:
                for triple in sentence["openie"]:
                    # spanを使って語句を特定
                    # token[span]にアクセス．形容詞だったり副詞などの修飾子を落とす
                    # triplesに入れる

                    triples.append(
                        {
                            "subject": self.drop_modifier(
                                sentence, triple["subjectSpan"]
                            ),
                            "relation": self.drop_modifier(
                                sentence, triple["relationSpan"]
                            ),
                            "object": self.drop_modifier(
                                sentence, triple["objectSpan"]
                            ),
                        }
                    )
            return triples
        else:
            return core_nlp_output

    def drop_modifier(self, sentence, span: list) -> str:
        obj = ""
        for idx in range(span[0], span[1]):
            tok = sentence["tokens"][idx]
            if "JJ" in tok["pos"]:
                continue
            if "RB" in tok["pos"]:
                continue
            obj = obj + " " + tok["word"]
        return obj.strip()

    def generate_graphviz_graph(self, text: str, png_filename: str = "./out/graph.png"):
        """
        :param (str | unicode) text: raw text for the CoreNLPServer to parse
        :param (list | string) png_filename: list of annotators to use
        """
        entity_relations = self.annotate(text, simple_format=True)
        """digraph G {
        # a -> b [ label="a to b" ];
        # b -> c [ label="another label"];
        }"""
        graph = list()
        graph.append("digraph {")
        for er in entity_relations:
            graph.append(
                '"{}" -> "{}" [ label="{}" ];'.format(
                    er["subject"], er["object"], er["relation"]
                )
            )
        graph.append("}")

        output_dir = os.path.join(".", os.path.dirname(png_filename))
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        out_dot = os.path.join(tempfile.gettempdir(), "graph.dot")
        with open(out_dot, "w") as output_file:
            output_file.writelines(graph)

        command = "dot -Tpng {} -o {}".format(out_dot, png_filename)
        dot_process = Popen(command, stdout=stderr, shell=True)
        dot_process.wait()
        assert (
            not dot_process.returncode
        ), "ERROR: Call to dot exited with a non-zero code status."

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def __del__(self):
        if hasattr(self, "client"):
            self.client.stop()
        del os.environ["CORENLP_HOME"]