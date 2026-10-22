# Local video packet framing and latency

The live encoder uses an **AVI envelope only on its local FFmpeg output pipe**.
The library's bounded `AviPictureParser` reads complete H.263 packet lengths,
then hands the original H.263 picture bytes to the existing modem worker. AVI
headers, timestamps and chunk tags never cross the modem link. H.245 negotiation,
96-byte AL3 segmentation and receiver interoperability behavior are unchanged.

This removes one avoidable picture interval from the sender. Previously the
elementary-stream parser needed the next picture start code to know that the
current picture was complete. At two frames per second that adds approximately
half a second, even when FFmpeg already finished encoding the current picture.

A synthetic local measurement with the live FFmpeg encoder options produced:

| Event | First picture | Second picture |
|---|---:|---:|
| Raw RGB frame supplied | 0.000 s | 0.503 s |
| Complete packet available from AVI | 0.076 s | 0.504 s |
| Previous elementary-parser behavior | About 0.501 s | About 1.003 s |

These timings measure the local software stage, not modem round-trip latency.
The regression test supplies exactly one raw frame and requires its encoded
picture before sending another frame or closing the stream.

FFmpeg must provide the AVI muxer as well as the required codecs. The dependency
dialog checks this before reporting Ready or allowing transmission; FFmpeg
remains an external dependency.

The receiver still uses FFmpeg's elementary H.263 parser. A separate test fed
complete pictures at 0.000, 0.504 and 1.003 seconds; decoded frames appeared at
0.506, 1.004 and 1.501 seconds. This retains approximately one received-picture
interval of lookahead. If transmission pauses, that interval can be longer.
The source's two-second video-overload restart also remains; audio continues.
The main window explicitly shows **Video paused; audio continues** until another
complete picture is admitted for transmission.

The receiver cannot safely interpret every AL3 SDU as a complete picture.
[H.324 (03/1996), section 6.6.1](https://www.itu.int/rec/T-REC-H.324-199603-S/en)
permits a picture to span multiple AL-SDUs while requiring H.263 picture starts
to align with SDU starts. The current profile advertises a maximum AL3 SDU of
1,024 bytes, distinct from its 4,096-byte retransmission buffer. This change
makes no new assumptions about peer picture boundaries or those limits.

The AVI parser accepts one 128 × 96 H.263 video stream, handles arbitrary pipe
fragmentation and RIFF padding, and bounds header/metadata and picture sizes.
Stop or encoder restart discards its pending container state. It is a local
encoder adapter, not a general AVI player or a new H.324 wire format.
