#!/usr/bin/env python
import sys
# Hack to add this to pythonpath
#sys.path.append('/Users/paulr/src/NICERsoft')
import matplotlib.pyplot as plt
import numpy as np
import argparse
from astropy import log
from astropy.table import Table, vstack
import astropy.io.fits as pyfits
import astropy.units as u
from astropy.time import Time
import copy
from os import path
from nicer.values import *
from cartographer import *
from functionality import *
from sci_plots import sci_plots
from eng_plots import eng_plots
from glob import glob

parser = argparse.ArgumentParser(description = "Plot the NICER data nicely.")
parser.add_argument("infiles", help="Input files", nargs='*')
parser.add_argument("--obsdir",help = "Find alllllllll the files!")
parser.add_argument("--object", help="Override object name", default=None)
parser.add_argument("--mask",help="Mask these IDS", nargs = '*', type=int, default=None)
parser.add_argument("-s", "--save", help = "Save plots to file", action = "store_true")
parser.add_argument("--sci", help = "Makes some nice science plots", action = "store_true")
parser.add_argument("--eng", help = "Makes some nice engineering plots", action = "store_true")
parser.add_argument("--filtswtrig", help = "Filter SW TRIG events", action = "store_true")
parser.add_argument("--filtovershoot", help = "Filter OVERSHOOT events", action = "store_true")
parser.add_argument("--filtundershoot", help = "Filter UNDERSHOOT events", action = "store_true")
parser.add_argument("--filtratio", help="Filter PHA/PHA_FAST ratio (argument is ratio to cut at)", type=float, default=0.0)
parser.add_argument("--filtall", help = "Filter SWTRIG, UNDERSHOOT and OVERSHOOT events", action = "store_true")
parser.add_argument("--emin", help="Minimum energy (keV) to keep", default=-1.0, type=float)
parser.add_argument("--emax", help="Minimum energy (keV) to keep", default=-1.0, type=float)
parser.add_argument("--tskip", help="Seconds to skip at beginning of data", default=0.0, type=float)
parser.add_argument("--lcbinsize", help="Light curve bin size (s)", default=0.5, type=float)
parser.add_argument("--pi", help="Force use of internal PHA to PI conversion", action='store_true')
parser.add_argument("--basename", help="Basename for output plots", default=None)
parser.add_argument("--lclog", help = "make light curve log axis", action = "store_true")
parser.add_argument("--pslog", help = "make power spectrum log axis", action = "store_true")
parser.add_argument("--writeps", help = "write out power spectrum", action = "store_true")
parser.add_argument("--nops", help="Disable power spectrum", action ="store_true")
parser.add_argument("--foldfreq", help="Make pulse profile by folding at a fixed freq (Hz)",
    default=0.0,type=float)
parser.add_argument("--nyquist", help="Nyquist freq for power spectrum (Hz)",
    default=100.0,type=float)
parser.add_argument("--map", help= "Creates a map with some stuff on it", action = 'store_true')
parser.add_argument("--orb", help="Path to orbit FITS filed", default = None)
parser.add_argument("--par", help="Path to par file", default = None)
args = parser.parse_args()

if args.obsdir:
    if len(args.infiles) == 0:
        args.infiles = glob(path.join(args.obsdir,'xti/event_cl/ni*.evt'))
        args.infiles.sort()
    if len(args.infiles) == 0:
        log.error("No event files found!")
    log.info('Found event files: {0}'.format("\n" + "    \n".join(args.infiles)))

    try:
        args.orb = glob(path.join(args.obsdir,'auxil/ni*.orb'))[0]
    except:
        log.error("Orbit file not found!")
    log.info('Found the orbit file: {0}'.format(args.orb))

    #getting the overshoot stuff
    hkfiles = glob(path.join(args.obsdir,'xti/hk/ni*.hk'))
    hkfiles.sort()
    log.info('Found the MPU housekeeping files: {0}'.format("\n"+"\t\n".join(hkfiles)))
    if len(hkfiles) > 1:
        log.info('Reading '+hkfiles[0])
        hdulist = pyfits.open(hkfiles[0])
        td = hdulist[1].data
        met = td['TIME']
        log.info("HK MET Range {0} to {1} (Span = {2:.1f} seconds)".format(met.min(),
            met.max(),met.max()-met.min()))
        t = MET0+met*u.s
        overshootrate = td['MPU_OVER_COUNT'].sum(axis=1)

        for fn in hkfiles[1:]:
            log.info('Reading '+fn)
            hdulist = pyfits.open(fn)
            mytd = hdulist[1].data
            mymet = td['TIME']
            myt = MET0+met*u.s
            myovershootrate = td['MPU_OVER_COUNT'].sum(axis=1)
            if not np.all(mymet == met):
                log.error('TIME axes are not compatible')
                sys.exit(1)
                overshootrate += myovershootrate
                log.info('Overshoot rate is: {0}'.format(np.mean(overshootrate)))
else:
    overshootrate = None

if args.filtall:
    args.filtswtrig=True
    args.filtovershoot=True
    args.filtundershoot=True
    args.filtratio=1.4
# Load files and build events table
log.info('Reading files')
tlist = []
for fn in args.infiles:
    log.info('Reading file {0}'.format(fn))
    tlist.append(Table.read(fn,hdu=1))

log.info('Concatenating files')
etable = vstack(tlist,metadata_conflicts='silent')
del tlist
# Change TIME column name to MET to reflect what it really is
etable.columns['TIME'].name = 'MET'

# Sort table by MET
etable.sort('MET')
log.info("Event MET Range : {0} to {1}".format(etable['MET'].min(),
    etable['MET'].max(), etable['MET'].max()-etable['MET'].min()))
log.info("TSTART {0}  TSTOP {1} (Span {2} seconds)".format(etable.meta['TSTART'],
    etable.meta['TSTOP'], etable.meta['TSTOP']-etable.meta['TSTART'] ))
log.info("DATE Range {0} to {1}".format(etable.meta['DATE-OBS'],
    etable.meta['DATE-END']))
if args.object is not None:
    etable.meta['OBJECT'] = args.object

# Hack to trim first chunk of data
if args.tskip > 0.0:
    t0 = etable.meta['TSTART']
    etable = etable[etable['MET']>t0+args.tskip]
    # Correct exposure (approximately)
    etable.meta['EXPOSURE'] -= args.tskip
    etable.meta['TSTART'] += args.tskip

# Add Time column with astropy Time for ease of use
log.info('Adding time column')
# This should really be done the FITS way using MJDREF etc...
# For now, just using MET0
etime = etable.columns['MET'] + MET0
etable['T'] = etime

# If there are no PI columns, add them with approximate calibration
if args.pi or not ('PI' in etable.colnames):
    log.info('Adding PI')
    calfile = 'data/gaincal_linear.txt'
    pi = calc_pi(etable,calfile)
    etable['PI'] = pi

#filtering out chosen IDS
if args.mask != None:
    log.info('Masking IDS')
    for id in args.mask:
            etable = etable[np.where(etable['DET_ID'] != id)]

# Note: To access event flags, use etable['EVENT_FLAGS'][:,B], where B is
# the bit number for the flag (e.g. FLAG_UNDERSHOOT)

exposure = etable.meta['EXPOSURE']
log.info('Exposure : {0:.2f}'.format(exposure))
log.info('Filtering...')

filt_str = 'Filter: {0:.2f} < E < {1:.2f} keV'.format(args.emin,args.emax)
if args.emin >= 0:
    b4 = etable['PI'] > args.emin/PI_TO_KEV
else:
    b4 = np.ones_like(etable['PI'],dtype=np.bool)
if args.emax >= 0:
    b4 = np.logical_and(b4, etable['PI']< args.emax/PI_TO_KEV)

# Apply filters for good events
if args.filtswtrig:
    b1 = etable['EVENT_FLAGS'][:,FLAG_SWTRIG] == False
    filt_str += ", not SWTRIG"
else:
    b1 = np.ones_like(etable['PI'],dtype=np.bool)
if args.filtundershoot:
    b2 = etable['EVENT_FLAGS'][:,FLAG_UNDERSHOOT] == False
    filt_str += ", not UNDERSHOOT"
else:
    b2 = np.ones_like(etable['PI'],dtype=np.bool)
if args.filtovershoot:
    b3 = etable['EVENT_FLAGS'][:,FLAG_OVERSHOOT] == False
    filt_str += ", not OVERSHOOT"
else:
    b3 = np.ones_like(etable['PI'],dtype=np.bool)

if args.filtratio > 0.0:
    ratio = np.zeros_like(etable['PI'],dtype=np.float)
    idx = np.where(np.logical_and(etable['PHA']>0, etable['PHA_FAST']>0))[0]
    ratio[idx] = np.asarray(etable['PHA'][idx],dtype=np.float)/np.asarray(etable['PHA_FAST'][idx],dtype=np.float)
    b5 = np.ones_like(etable['PI'],dtype=np.bool)
    b5[ratio>args.filtratio] = False
    filt_str += ", ratio < {0:.2f}".format(args.filtratio)
else:
    b5 = np.ones_like(etable['PI'],dtype=np.bool)

idx = np.where(b1 & b2 & b3 & b4 & b5)[0]
del b1, b2, b3, b4, b5
filttable = etable[idx]
filttable.meta['FILT_STR'] = filt_str

log.info("Filtering cut {0} events to {1} ({2:.2f}%)".format(len(etable),
    len(filttable), 100*len(filttable)/len(etable)))

if args.basename is None:
    bn = path.basename(args.infiles[0]).split('_')[0]
    basename = 'ql-{0}'.format(bn)
    log.info('OBS_ID {0}'.format(etable.meta['OBS_ID']))
    if etable.meta['OBS_ID'].startswith('000000'):
        log.info('Overwriting OBS_ID')
        etable.meta['OBS_ID'] = bn
        filttable.meta['OBS_ID'] = bn
else:
    basename = args.basename

if not args.sci and not args.eng and not args.map:
    log.warning("No plot requested, making sci and eng")
    args.sci = True
    args.eng = True

if overshootrate is None:
    overshootrate = np.zeros(len(etable['MET']))

#Making all the specified or unspecified plots below
if args.eng:
    figure1 = eng_plots(filttable)
    figure1.set_size_inches(16,12)
    if args.save:
    	log.info('Writing eng plot {0}'.format(basename))
    	if args.filtall:
        	figure1.savefig('{0}_eng_FILT.png'.format(basename), dpi = 100)
    	else:
        	figure1.savefig('{0}_eng.png'.format(basename), dpi = 100)
    else:
        log.info('Tryingto show the eng plot')
        plt.show()

if args.sci:
    # Make science plots using filtered events
    figure2 = sci_plots(filttable, args.lclog, args.lcbinsize, args.foldfreq, args.nyquist,
        args.pslog, args.writeps, args.nops, overshootrate, args.orb, args.par)
    figure2.set_size_inches(16,12)
    if args.save:
    	log.info('Writing sci plot {0}'.format(basename))
    	if args.filtall:
        	figure2.savefig('{0}_sci_FILT.png'.format(basename), dpi = 100)
    	else:
        	figure2.savefig('{0}_sci.png'.format(basename), dpi = 100)
    else:
        log.info('Trying to show the sci plot')
    	plt.show()

if args.map:
    log.info("I'M THE MAP I'M THE MAP I'M THE MAAAAP")
    figure3 = cartography(etable, overshootrate)
    figure3.set_size_inches(16,12)

    if args.save:
        log.info('Writing MAP {0}'.format(basename))
        if args.filtall:
            figure3.savefig('{0}_map_FILT.png'.format(basename), dpi = 100)
    	else:
            figure3.savefig('{0}_map.png'.format(basename), dpi = 100)
    else:
        plt.show()
